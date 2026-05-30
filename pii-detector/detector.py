"""Deterministic + hybrid PII detector for schema column descriptors.

Three implementation tiers (Option C — Hybrid):
  Tier 1 — Rule engine   : Weighted rule scoring; no API calls.  If rule
                            confidence ≥ auto_tag_threshold the result is
                            returned immediately (fast path).
  Tier 2 — Embeddings    : sentence-transformers cosine similarity vs. PII
                            category prototypes.  Blended with rule score.
                            Used when rules are uncertain (< auto_tag_threshold).
  Tier 3 — LLM fallback  : OpenAI structured-output call (gpt-4o-mini by
                            default).  Invoked only when the blended score is
                            still below the review threshold AND an
                            OPENAI_API_KEY is present in the environment.
                            Degrades gracefully to the embedding result if no
                            key is configured.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import ipaddress
import json
import logging
import os
import re
from typing import Any

import numpy as np
from pii_patterns import (
    BOOLEAN_LIKE_VALUES,
    CATEGORY_RULES,
    NEGATIVE_CONTEXT_TOKENS,
    NON_INFORMATIVE_SAMPLE_VALUES,
    PII_CATEGORY_TO_MASKING_FUNCTION,
    REQUIRED_PII_CATEGORIES,
)

logger = logging.getLogger(__name__)


@dataclass
class CategoryScore:
    """Internal scoring breakdown for a single PII category."""

    category: str
    score: float
    evidence: list[str]
    evidence_types: set[str]


class PiiDetector:
    """Detect likely PII columns from schema descriptors using weighted rules."""

    auto_tag_threshold = 0.85
    review_threshold = 0.60
    ambiguous_threshold = 0.50
    tie_break_delta = 0.10

    def detect(self, column: dict[str, Any]) -> dict[str, Any]:
        """Classify a single column descriptor."""

        table_name = str(column.get("table_name", ""))
        column_name = str(column.get("column_name", ""))
        data_type = str(column.get("data_type", ""))
        sample_values = column.get("sample_values") or []

        name_tokens = self._tokenize(column_name)
        table_tokens = self._tokenize(table_name)
        name_text = "_".join(name_tokens)
        data_type_normalized = data_type.lower()
        cleaned_samples = self._clean_sample_values(sample_values)

        scores = [
            self._score_category(
                category=category,
                name_text=name_text,
                name_tokens=name_tokens,
                table_tokens=table_tokens,
                data_type=data_type_normalized,
                sample_values=cleaned_samples,
            )
            for category in REQUIRED_PII_CATEGORIES
        ]
        scores.sort(key=lambda result: result.score, reverse=True)

        top = scores[0]
        second = scores[1] if len(scores) > 1 else CategoryScore("NONE", 0.0, [], set())
        ambiguous = top.score >= self.ambiguous_threshold and (top.score - second.score) < self.tie_break_delta

        confidence = min(0.99, max(0.01, top.score - (0.05 if ambiguous else 0.0)))
        confidence = round(confidence, 2)

        is_pii = confidence >= self.review_threshold or ambiguous
        review_required = False
        if is_pii:
            review_required = confidence < self.auto_tag_threshold or ambiguous
        elif ambiguous:
            review_required = True

        pii_category = top.category if is_pii else None
        masking_function = (
            PII_CATEGORY_TO_MASKING_FUNCTION.get(top.category) if is_pii else None
        )

        if is_pii:
            reasoning = self._build_positive_reasoning(top, second, review_required)
        else:
            reasoning = self._build_negative_reasoning(top, second, review_required)

        return {
            "table_name": table_name,
            "column_name": column_name,
            "is_pii": is_pii,
            "confidence": confidence,
            "pii_category": pii_category,
            "recommended_masking_function": masking_function,
            "review_required": review_required,
            "reasoning": reasoning,
        }

    def detect_all(self, columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Classify a list of schema column descriptors."""

        return [self.detect(column) for column in columns]

    def _score_category(
        self,
        category: str,
        name_text: str,
        name_tokens: list[str],
        table_tokens: list[str],
        data_type: str,
        sample_values: list[str],
    ) -> CategoryScore:
        rule = CATEGORY_RULES[category]
        evidence: list[str] = []
        evidence_types: set[str] = set()
        score = 0.0

        phrase_score, phrase_evidence = self._match_phrases(name_text, rule["phrases"])
        if phrase_score:
            score += phrase_score
            evidence.append(phrase_evidence)
            evidence_types.add("name")

        token_score, token_evidence = self._match_tokens(name_tokens, rule["tokens"])
        if token_score:
            score += token_score
            evidence.append(token_evidence)
            evidence_types.add("name")

        table_score, table_evidence = self._match_tokens(table_tokens, rule["table_tokens"], cap=0.08)
        if table_score:
            score += table_score
            evidence.append(table_evidence)
            evidence_types.add("table")

        type_score, type_evidence = self._score_data_type(category, data_type)
        if type_score:
            score += type_score
            evidence.append(type_evidence)
            evidence_types.add("type")

        sample_score, sample_evidence = self._score_sample_values(
            category=category,
            name_tokens=name_tokens,
            data_type=data_type,
            sample_values=sample_values,
        )
        if sample_score:
            score += sample_score
            evidence.append(sample_evidence)
            evidence_types.add("sample")

        penalty, penalty_evidence = self._score_penalties(name_tokens, data_type, sample_values)
        if penalty:
            score -= penalty
            evidence.append(penalty_evidence)

        score = max(0.0, min(0.98, score))
        return CategoryScore(category=category, score=score, evidence=evidence, evidence_types=evidence_types)

    def _match_phrases(self, text: str, phrases: dict[str, float]) -> tuple[float, str | None]:
        matched = [(phrase, weight) for phrase, weight in phrases.items() if phrase in text]
        if not matched:
            return 0.0, None
        phrase, weight = max(matched, key=lambda item: item[1])
        return weight, f"column name matches '{phrase}'"

    def _match_tokens(
        self, tokens: list[str], weighted_tokens: dict[str, float], cap: float = 0.22
    ) -> tuple[float, str | None]:
        matched = [(token, weight) for token, weight in weighted_tokens.items() if token in tokens]
        if not matched:
            return 0.0, None
        total = min(cap, sum(weight for _, weight in matched))
        token_list = ", ".join(token for token, _ in matched[:3])
        return total, f"tokens suggest PII ({token_list})"

    def _score_data_type(self, category: str, data_type: str) -> tuple[float, str | None]:
        if category == "DATE_OF_BIRTH" and any(token in data_type for token in ("date", "timestamp")):
            return 0.08, f"data type '{data_type}' supports date-like values"
        if category == "FULL_NAME" and any(token in data_type for token in ("char", "text", "string", "varchar")):
            return 0.04, f"data type '{data_type}' is text-oriented"
        if category in {"EMAIL", "PHONE", "ADDRESS", "IP_ADDRESS", "ACCOUNT_NUMBER", "NATIONAL_ID"} and any(
            token in data_type for token in ("char", "text", "string", "varchar")
        ):
            return 0.03, f"data type '{data_type}' is compatible with structured identifiers"
        return 0.0, None

    def _score_sample_values(
        self,
        category: str,
        name_tokens: list[str],
        data_type: str,
        sample_values: list[str],
    ) -> tuple[float, str | None]:
        if not sample_values:
            return 0.0, None

        if category == "EMAIL":
            hits = [value for value in sample_values if self._is_email(value)]
            if hits:
                return 0.55, "sample values match email format"

        if category == "PHONE":
            hits = [value for value in sample_values if self._is_phone(value)]
            if hits:
                return 0.45, "sample values look like phone numbers"

        if category == "SSN":
            hits = [value for value in sample_values if self._is_ssn(value)]
            if hits:
                return 0.55, "sample values match SSN format"

        if category == "CREDIT_CARD":
            hits = [value for value in sample_values if self._is_credit_card(value)]
            if hits:
                return 0.62, "sample values pass credit-card checks"

        if category == "ACCOUNT_NUMBER":
            hits = [value for value in sample_values if self._is_account_number(value)]
            if hits:
                return 0.42, "sample values resemble account identifiers"

        if category == "DATE_OF_BIRTH":
            hits = [value for value in sample_values if self._is_date_value(value)]
            if hits:
                if any(token in name_tokens for token in ("dob", "birth", "birthday", "nacimiento")):
                    return 0.36, "sample values are date-like and align with birth-related naming"
                return 0.10, "sample values are date-like"

        if category == "ADDRESS":
            hits = [value for value in sample_values if self._is_address(value)]
            if hits:
                return 0.48, "sample values look like street or mailing addresses"

        if category == "IP_ADDRESS":
            hits = [value for value in sample_values if self._is_ip_address(value)]
            if hits:
                return 0.64, "sample values are valid IP addresses"

        if category == "FULL_NAME":
            hits = [value for value in sample_values if self._is_person_name(value)]
            if hits:
                return 0.34, "sample values look like personal names"

        if category == "NATIONAL_ID":
            hits = [value for value in sample_values if self._is_national_id(value)]
            if hits:
                return 0.34, "sample values resemble government-issued identifiers"

        return 0.0, None

    def _score_penalties(
        self, name_tokens: list[str], data_type: str, sample_values: list[str]
    ) -> tuple[float, str | None]:
        matched = [(token, weight) for token, weight in NEGATIVE_CONTEXT_TOKENS.items() if token in name_tokens]
        penalty = min(0.40, sum(weight for _, weight in matched)) if matched else 0.0

        evidence_parts: list[str] = []
        if penalty:
            token_list = ", ".join(token for token, _ in matched[:3])
            evidence_parts.append(f"context tokens reduce confidence ({token_list})")

        if sample_values and all(value in BOOLEAN_LIKE_VALUES for value in sample_values):
            penalty += 0.35
            evidence_parts.append("boolean-like sample values do not look like raw PII")

        if "bool" in data_type:
            penalty += 0.20
            evidence_parts.append("boolean data type is unlikely to store raw PII")

        penalty = min(0.55, penalty)
        if not evidence_parts:
            return 0.0, None
        return penalty, "; ".join(evidence_parts)

    def _build_positive_reasoning(
        self, top: CategoryScore, second: CategoryScore, review_required: bool
    ) -> str:
        evidence = "; ".join(part for part in top.evidence if part)
        reasoning = f"Detected {top.category} because {evidence}."
        if review_required:
            reasoning += (
                f" Review required because confidence is below {self.auto_tag_threshold:.2f}"
                f" or the signal overlaps with {second.category}."
            )
        return reasoning

    def _build_negative_reasoning(
        self, top: CategoryScore, second: CategoryScore, review_required: bool
    ) -> str:
        if review_required:
            return (
                f"No auto-classification. The strongest signals were {top.category} ({top.score:.2f}) "
                f"and {second.category} ({second.score:.2f}), so this should be reviewed by a human."
            )
        if top.evidence:
            return (
                f"No strong PII classification. Weak signals pointed to {top.category}, "
                f"but they were not strong enough to cross the review threshold."
            )
        return "No strong PII naming or sample-value patterns were detected."

    def _clean_sample_values(self, sample_values: list[Any]) -> list[str]:
        cleaned: list[str] = []
        for value in sample_values:
            text = str(value).strip()
            if not text:
                continue
            normalized = text.lower()
            if normalized in NON_INFORMATIVE_SAMPLE_VALUES:
                continue
            cleaned.append(text)
        return cleaned

    def _tokenize(self, text: str) -> list[str]:
        if not text:
            return []
        text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
        text = text.replace("-", "_").replace(".", "_").replace("/", "_")
        text = re.sub(r"[^a-zA-Z0-9_]+", " ", text)
        tokens = [token.lower() for token in re.split(r"[\s_]+", text) if token]
        return tokens

    def _digits_only(self, value: str) -> str:
        return re.sub(r"\D", "", value)

    def _is_email(self, value: str) -> bool:
        return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value.strip(), flags=re.IGNORECASE))

    def _is_phone(self, value: str) -> bool:
        digits = self._digits_only(value)
        if not 10 <= len(digits) <= 15:
            return False
        return bool(re.search(r"[+\-().\s]", value)) or value.startswith("+")

    def _is_ssn(self, value: str) -> bool:
        stripped = value.strip()
        digits = self._digits_only(stripped)
        return bool(re.fullmatch(r"\d{3}-\d{2}-\d{4}", stripped) or re.fullmatch(r"\*{3}-\*{2}-\d{4}", stripped) or len(digits) == 9)

    def _is_credit_card(self, value: str) -> bool:
        digits = self._digits_only(value)
        if not 13 <= len(digits) <= 19:
            return False
        return self._passes_luhn(digits)

    def _is_account_number(self, value: str) -> bool:
        stripped = value.strip().upper()
        digits = self._digits_only(stripped)
        if re.fullmatch(r"\*{2,}\d{3,6}", stripped):
            return True
        if stripped.startswith(("ACC", "ACCT", "IBAN")) and len(digits) >= 4:
            return True
        return bool(re.fullmatch(r"[A-Z0-9-]{8,24}", stripped) and len(digits) >= 6)

    def _is_date_value(self, value: str) -> bool:
        formats = ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d")
        for fmt in formats:
            try:
                parsed = datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
            if date(1900, 1, 1) <= parsed <= date.today():
                return True
        return False

    def _is_address(self, value: str) -> bool:
        normalized = value.strip().lower()
        street_tokens = ("street", "st", "road", "rd", "avenue", "ave", "lane", "ln", "drive", "dr", "blvd", "boulevard")
        has_street_word = any(token in normalized.split() for token in street_tokens)
        has_number = bool(re.search(r"\d", normalized))
        return has_number and has_street_word

    def _is_ip_address(self, value: str) -> bool:
        try:
            ipaddress.ip_address(value.strip())
            return True
        except ValueError:
            return False

    def _is_person_name(self, value: str) -> bool:
        normalized = re.sub(r"[^A-Za-z\s'-]", "", value).strip()
        if not normalized or "@" in value:
            return False
        parts = [part for part in normalized.split() if part]
        return 1 <= len(parts) <= 4 and all(len(part) >= 2 for part in parts)

    def _is_national_id(self, value: str) -> bool:
        stripped = value.strip().upper()
        digits = self._digits_only(stripped)
        if re.fullmatch(r"\d{4}\s\d{4}\s\d{4}", value.strip()):
            return True
        if re.fullmatch(r"[A-Z]{2}\d{6,12}", stripped):
            return True
        return 8 <= len(digits) <= 14

    def _passes_luhn(self, digits: str) -> bool:
        checksum = 0
        reverse_digits = digits[::-1]
        for index, char in enumerate(reverse_digits):
            number = int(char)
            if index % 2 == 1:
                number *= 2
                if number > 9:
                    number -= 9
            checksum += number
        return checksum % 10 == 0


# ---------------------------------------------------------------------------
# Option C — Hybrid PII Detector
# ---------------------------------------------------------------------------

class HybridPiiDetector(PiiDetector):
    """Three-tier hybrid PII detector (Option C).

    Detection cascade:
      1. **Rule engine** (this class's parent): instant, zero API cost.
         If confidence ≥ ``auto_tag_threshold`` (0.85) → return immediately.
      2. **Embedding similarity** (sentence-transformers ``all-MiniLM-L6-v2``):
         Column descriptor is compared against per-category prototype texts
         using cosine similarity.  Blended 40 % rule + 60 % embedding.
         Used when rule confidence < ``auto_tag_threshold``.
      3. **LLM** (``gpt-4o-mini`` via OpenAI API):
         Only invoked when blended confidence < ``EMBEDDING_HIGH_CONF`` *and*
         ``OPENAI_API_KEY`` is set in the environment.  If no key is
         configured the detector degrades gracefully to the embedding result.

    Every result dict contains a ``"detection_method"`` key set to one of:
    ``"rules"``, ``"embedding"``, ``"llm"``, or ``"rules+embedding"``.
    """

    # ------------------------------------------------------------------
    # Rich natural-language prototype texts for each PII category.
    # These drive the embedding similarity tier.
    # ------------------------------------------------------------------
    _PROTOTYPES: dict[str, str] = {
        "FULL_NAME": (
            "full name person name first name last name given name family name "
            "surname forename customer name employee name contact name user name "
            "legal name display name preferred name beneficiary name"
        ),
        "EMAIL": (
            "email address e-mail user email contact email email address field "
            "customer email employee email login email notification email "
            "reply to address correspondence email"
        ),
        "PHONE": (
            "phone number telephone number mobile number cell phone number "
            "contact number work phone home phone fax number SMS number "
            "WhatsApp number primary phone secondary phone"
        ),
        "SSN": (
            "social security number SSN social insurance number SIN "
            "tax identification number TIN national tax id 123-45-6789 "
            "government issued identity number federal taxpayer id"
        ),
        "CREDIT_CARD": (
            "credit card number debit card number payment card number "
            "card number PAN primary account number VISA MasterCard Amex "
            "billing card card on file payment instrument"
        ),
        "ACCOUNT_NUMBER": (
            "account number bank account number IBAN BBAN financial account "
            "checking account savings account routing number ledger account "
            "customer account identifier member account"
        ),
        "DATE_OF_BIRTH": (
            "date of birth birthday birth date DOB birth year age date "
            "date born year of birth date of birth field patient birthdate "
            "customer birthdate employee date of birth"
        ),
        "ADDRESS": (
            "address street address mailing address billing address shipping "
            "address home address work address postal address city state zip "
            "postal code country province region street name house number "
            "apartment suite"
        ),
        "IP_ADDRESS": (
            "IP address IPv4 address IPv6 address network address host address "
            "client IP source IP destination IP remote addr user IP login IP "
            "device IP 192.168.1.1 10.0.0.1"
        ),
        "NATIONAL_ID": (
            "national ID national identification number passport number "
            "driver licence number national insurance number NRIC Aadhaar "
            "government ID voter ID citizen ID resident registration number "
            "identity document number"
        ),
    }

    # ------------------------------------------------------------------
    # Thresholds
    # ------------------------------------------------------------------
    # Rule tier: score above this → instant return, skip AI tiers
    _RULE_FAST_PATH: float = 0.85

    # Blended score (0.4*rule + 0.6*embedding) above this → return without LLM
    _EMBEDDING_HIGH_CONF: float = 0.72

    # Blended score below this AND LLM is available → call LLM
    _LLM_TRIGGER: float = 0.72

    # Blend weights
    _RULE_WEIGHT: float = 0.40
    _EMBED_WEIGHT: float = 0.60

    # ------------------------------------------------------------------
    # Class-level lazy caches (shared across all instances)
    # ------------------------------------------------------------------
    _st_model = None          # SentenceTransformer instance
    _proto_embeddings = None  # np.ndarray (n_categories, embed_dim)
    _proto_categories: list[str] = []

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def detect(self, column: dict) -> dict:  # type: ignore[override]
        """Classify a single column descriptor using the three-tier cascade."""
        # --- Tier 1: rule engine ---
        result = super().detect(column)
        rule_conf = float(result.get("confidence", 0.0))

        if rule_conf >= self._RULE_FAST_PATH:
            result["detection_method"] = "rules"
            return result

        # Build a concise text representation of the column.
        descriptor_text = self._column_to_text(column)

        # --- Tier 2: embedding similarity ---
        try:
            best_category, embed_sim = self._embedding_classify(descriptor_text)
        except Exception as exc:
            logger.warning("Embedding tier failed: %s — using rule result", exc)
            result["detection_method"] = "rules"
            return result

        # Blended score weights embedding more than rules for ambiguous cases.
        blended = self._RULE_WEIGHT * rule_conf + self._EMBED_WEIGHT * embed_sim

        if blended >= self._EMBEDDING_HIGH_CONF and best_category:
            result = self._build_ai_result(
                column=column,
                category=best_category,
                confidence=min(blended, 0.99),
                reasoning=(
                    f"Embedding similarity {embed_sim:.2f} for {best_category}; "
                    f"blended score {blended:.2f} (rule {rule_conf:.2f} + "
                    f"embed {embed_sim:.2f})"
                ),
            )
            result["detection_method"] = "embedding"
            return result

        # --- Tier 3: LLM ---
        if blended < self._LLM_TRIGGER:
            llm_result = self._llm_classify(column, descriptor_text)
            if llm_result is not None:
                llm_result["detection_method"] = "llm"
                return llm_result

        # Fallback: return rule result enriched with embedding context.
        if embed_sim > rule_conf and best_category:
            result["reasoning"] = (
                result.get("reasoning", "")
                + f"  [Embedding: {best_category} sim={embed_sim:.2f}]"
            )
        result["detection_method"] = "rules+embedding"
        return result

    def detect_all(self, columns: list[dict]) -> list[dict]:  # type: ignore[override]
        """Batch detect — delegates to ``detect`` for each column."""
        return [self.detect(col) for col in columns]

    # ------------------------------------------------------------------
    # Tier 2 — Embedding helpers
    # ------------------------------------------------------------------

    def _column_to_text(self, column: dict) -> str:
        """Serialise a column descriptor to a flat string for embedding."""
        parts: list[str] = []
        if column.get("column_name"):
            parts.append(str(column["column_name"]))
        if column.get("table_name"):
            parts.append(str(column["table_name"]))
        if column.get("data_type"):
            parts.append(str(column["data_type"]))
        if column.get("description"):
            parts.append(str(column["description"]))
        samples = column.get("sample_values", [])
        if isinstance(samples, list):
            parts.extend(str(s) for s in samples[:5] if s is not None)
        return " ".join(parts)

    def _embedding_classify(self, text: str) -> tuple[str | None, float]:
        """Return (best_pii_category, cosine_similarity) using sentence-transformers."""
        model = self._get_st_model()
        proto_embs = self._get_prototype_embeddings(model)

        col_emb = model.encode([text], convert_to_numpy=True, show_progress_bar=False)
        # cosine similarity: dot product of unit vectors
        col_norm = col_emb / (np.linalg.norm(col_emb, axis=1, keepdims=True) + 1e-9)
        proto_norm = proto_embs / (
            np.linalg.norm(proto_embs, axis=1, keepdims=True) + 1e-9
        )
        sims = (col_norm @ proto_norm.T).flatten()  # (n_categories,)

        best_idx = int(np.argmax(sims))
        best_sim = float(sims[best_idx])
        best_cat = self._proto_categories[best_idx]
        return best_cat, best_sim

    @classmethod
    def _get_st_model(cls):
        """Lazy-load the sentence-transformer model (class-level singleton).

        Patches ``transformers.safetensors_conversion.auto_conversion`` to a
        no-op before loading so the model loader never spawns the background
        thread that attempts a safetensors conversion check against the
        HuggingFace Hub (which fails with SSL errors on macOS corporate
        networks).  Falls back to a live download only when the local cache is
        missing.
        """
        if cls._st_model is None:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415

            model_name = "sentence-transformers/all-MiniLM-L6-v2"

            # Suppress the background safetensors-conversion network call.
            # modeling_utils does ``from .safetensors_conversion import
            # auto_conversion`` so we must patch the name in *modeling_utils*,
            # not in the safetensors_conversion module.
            try:
                import transformers.modeling_utils as _mu  # noqa: PLC0415

                _orig = _mu.auto_conversion
                _mu.auto_conversion = lambda *a, **kw: None
                _sc = _mu
            except Exception:
                _orig = None
                _sc = None

            try:
                cls._st_model = SentenceTransformer(
                    model_name, local_files_only=True
                )
                logger.info(
                    "Loaded sentence-transformer model from local cache: %s",
                    model_name,
                )
            except Exception:
                logger.info("Local cache miss — downloading %s", model_name)
                cls._st_model = SentenceTransformer(model_name)
            finally:
                # Restore the original function in case other code relies on it.
                if _sc is not None and _orig is not None:
                    _sc.auto_conversion = _orig

        return cls._st_model

    @classmethod
    def _get_prototype_embeddings(cls, model) -> "np.ndarray":
        """Compute (and cache) prototype embeddings for all PII categories."""
        if cls._proto_embeddings is None:
            cls._proto_categories = list(cls._PROTOTYPES.keys())
            texts = [cls._PROTOTYPES[c] for c in cls._proto_categories]
            cls._proto_embeddings = model.encode(
                texts, convert_to_numpy=True, show_progress_bar=False
            )
            logger.info(
                "Cached %d PII category prototype embeddings", len(cls._proto_categories)
            )
        return cls._proto_embeddings

    # ------------------------------------------------------------------
    # Tier 3 — LLM helpers
    # ------------------------------------------------------------------

    def _llm_classify(self, column: dict, descriptor_text: str) -> dict | None:
        """Call OpenAI gpt-4o-mini to classify the column.

        Returns a result dict on success; ``None`` if the API is unavailable or
        the call fails (enabling graceful fallback to the embedding result).
        """
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return None

        try:
            import openai  # noqa: PLC0415

            client = openai.OpenAI(api_key=api_key)
        except Exception as exc:
            logger.warning("OpenAI client init failed: %s", exc)
            return None

        categories_list = ", ".join(self._PROTOTYPES.keys())
        prompt = (
            "You are a data-privacy expert.  Analyse the following database "
            "column descriptor and determine whether it contains personally "
            "identifiable information (PII).\n\n"
            f"Column descriptor (JSON):\n{json.dumps(column, indent=2)}\n\n"
            "Respond ONLY with a single JSON object — no markdown, no extra "
            "text — with the following fields:\n"
            '  "is_pii": boolean\n'
            f'  "pii_category": one of [{categories_list}] or null if not PII\n'
            '  "confidence": float 0.0–1.0\n'
            '  "reasoning": one-sentence explanation\n'
        )
        try:
            response = client.chat.completions.create(
                model=os.getenv("DEFAULT_CHAT_MODEL", "gpt-4o-mini"),
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=256,
            )
            raw = response.choices[0].message.content or "{}"
            parsed = json.loads(raw)
        except Exception as exc:
            logger.warning("LLM call failed: %s", exc)
            return None

        is_pii = bool(parsed.get("is_pii", False))
        category = parsed.get("pii_category") or None
        confidence = float(parsed.get("confidence", 0.5))
        reasoning = str(parsed.get("reasoning", "LLM classification"))

        if not is_pii or category not in self._PROTOTYPES:
            return {
                "table_name": str(column.get("table_name", "")),
                "column_name": str(column.get("column_name", "")),
                "is_pii": False,
                "pii_category": None,
                "confidence": confidence,
                "recommended_masking_function": None,
                "review_required": False,
                "reasoning": reasoning,
            }

        return self._build_ai_result(
            column=column,
            category=category,
            confidence=confidence,
            reasoning=reasoning,
        )

    # ------------------------------------------------------------------
    # Result builder
    # ------------------------------------------------------------------

    def _build_ai_result(
        self,
        column: dict,
        category: str,
        confidence: float,
        reasoning: str,
    ) -> dict:
        """Construct a result dict in the same shape as PiiDetector.detect()."""
        review_required = confidence < self.auto_tag_threshold
        return {
            "table_name": str(column.get("table_name", "")),
            "column_name": str(column.get("column_name", "")),
            "is_pii": True,
            "pii_category": category,
            "confidence": round(confidence, 4),
            "recommended_masking_function": PII_CATEGORY_TO_MASKING_FUNCTION.get(category),
            "review_required": review_required,
            "reasoning": reasoning,
        }
