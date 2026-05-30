"""Deterministic PII detector for schema column descriptors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import ipaddress
import re
from typing import Any

from pii_patterns import (
    BOOLEAN_LIKE_VALUES,
    CATEGORY_RULES,
    NEGATIVE_CONTEXT_TOKENS,
    NON_INFORMATIVE_SAMPLE_VALUES,
    PII_CATEGORY_TO_MASKING_FUNCTION,
    REQUIRED_PII_CATEGORIES,
)


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
