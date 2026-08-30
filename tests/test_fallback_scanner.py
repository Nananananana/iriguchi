"""The fallback scanner: what it catches, what it also catches, and what it misses.

Three kinds of test, and the middle one is the unusual one.

**What it catches** is ordinary. **What it also catches** is written down rather
than apologised for: ADR-0005 says this scanner is allowed to be wrong in one
direction, so its over-detections are specified behaviour and a change that
removed one would be a change worth noticing. **What it misses** is the most
important section in the file, because a scanner's silence is the thing people
mistake for coverage.

The suite also does the job `tests/contracts.py` says it cannot: assert on the
*value* under each span. The port's offset clause is a bounds check, which
catches normalization that expands and cannot catch normalization that
contracts. Only an adapter knows what it meant to point at, so only an adapter
can check.
"""

from __future__ import annotations

import pytest

from contracts import SensitivityScannerContract
from iriguchi.domain.sensitivity import Sensitivity, SensitivityLevel
from iriguchi.infrastructure.scanners.fallback import FallbackScanner
from iriguchi.ports.scanner import SensitivityScanner


def found(text: str) -> list[tuple[str, str]]:
    """Every finding as `(short rule name, the text under its span)`."""
    return [
        (finding.rule.removeprefix("fallback."), text[finding.span.start : finding.span.end])
        for finding in FallbackScanner().scan(text)
    ]


#: Assembled rather than written out. `pre-commit`'s `detect-private-key` hook
#: matches the literal header wherever it appears, and it is right to: a test
#: file is exactly where somebody pastes a real key while debugging. Splitting
#: the string keeps the hook armed across the whole repository -- including over
#: this file -- while still exercising the rule.
PEM_HEADER = "-----BEGIN RSA " + "PRIVATE KEY-----"


def rules(text: str) -> set[str]:
    return {rule for rule, _ in found(text)}


class TestTheContract(SensitivityScannerContract):
    def make_scanner(self) -> SensitivityScanner:
        return FallbackScanner()


class TestWhatItCatches:
    @pytest.mark.parametrize(
        ("text", "rule", "value"),
        [
            ("Contact tanaka@example.com by Friday.", "email-shape", "tanaka@example.com"),
            ("メールは a@b.co です", "email-shape", "a@b.co"),
            ("password: hunter2sekret", "credential-context", "hunter2sekret"),
            ("パスワード＝ correcthorse", "credential-context", "correcthorse"),
            ("api_key = AKIAIOSFODNN7EXAMPLE", "vendor-key-prefix", "AKIAIOSFODNN7EXAMPLE"),
            (
                "token ghp_abcdefghijklmnopqrstuvwxyz01",
                "vendor-key-prefix",
                "ghp_abcdefghijklmnopqrstuvwxyz01",
            ),
            ("https://admin:hunter2@internal.example.com", "url-credentials", "admin:hunter2"),
            ("電話は 09012345678 です", "long-digit-run", "09012345678"),
            ("田中さんに連絡してください", "japanese-honorific", "田中さん"),
        ],
    )
    def test_it_finds_the_right_characters(self, text: str, rule: str, value: str) -> None:
        assert (rule, value) in found(text)

    def test_it_finds_a_full_width_address(self) -> None:
        """The reason normalization exists at all.

        Missing this would send the prompt **out**, which is the direction that
        cannot be undone -- so matching on raw text was never an option.
        """
        text = "ｔａｎａｋａ＠ｅｘａｍｐｌｅ．ｃｏｍ にご連絡ください"
        assert ("email-shape", "ｔａｎａｋａ＠ｅｘａｍｐｌｅ．ｃｏｍ") in found(text)

    def test_a_digit_run_fires_next_to_kanji(self) -> None:
        """No `\\b` in that rule, and this is why.

        Kanji are word characters, so `\\b\\d{8,}\\b` never fires inside
        `番号123456789012です`. mamori learned this the expensive way and wrote
        it down; the rule uses explicit lookarounds instead.
        """
        assert ("long-digit-run", "123456789012") in found("番号123456789012です")

    def test_it_finds_a_pem_header(self) -> None:
        assert ("private-key-block", PEM_HEADER) in found(PEM_HEADER)

    def test_a_high_entropy_token_is_found_without_any_prefix(self) -> None:
        """What the vendor list cannot do: an unknown vendor, or no vendor."""
        text = "use dGhpcyBpcyBhIHNlY3JldCB2YWx1ZSBmb3IgdGVzdGluZw== to authenticate"
        assert "high-entropy-token" in rules(text)


class TestWhatItAlsoCatches:
    """Specified over-detection, not tolerated over-detection. ADR-0005.

    Each of these routes a safe prompt to the local model. The person gets a
    worse answer and can say so, which is the failure this project is willing to
    have.
    """

    def test_an_order_number_looks_exactly_like_a_card_number(self) -> None:
        """The most over-detecting rule here, and the least fixable.

        Ten symbols cap a digit string's entropy at 3.32 bits, so no threshold
        separates these two. A checksum would, and checksums are mamori's job.
        """
        assert "long-digit-run" in rules("order ORD-2026-0000148372 shipped")
        assert "long-digit-run" in rules("カード番号は 4111111111111111 です")

    def test_an_epoch_timestamp_is_a_finding(self) -> None:
        assert "long-digit-run" in rules("the event fired at 1756512000")

    def test_a_title_is_swept_up_with_the_name(self) -> None:
        """Nothing here knows where a title ends, so the run reaches back."""
        assert ("japanese-honorific", "業部長の田中さん") in found("営業部長の田中さん")

    def test_a_stoplisted_honorific_is_not_a_finding(self) -> None:
        """The stoplist is why the external route is reachable in practice.

        `お母さん` and `皆さん` appear in a large share of Japanese prompts. A
        scanner that reports a finding in all of them makes every prompt local,
        which is not caution -- it is a broken router.
        """
        assert not found("皆さんお疲れ様です")
        assert "japanese-honorific" not in rules("お母さんに聞いてみます")

    def test_the_stoplist_does_not_hide_a_real_name_beside_it(self) -> None:
        assert any("佐藤さん" in value for _, value in found("お母さんと佐藤さんへ"))


class TestWhatItMisses:
    """The section that matters most.

    A scanner's silence is what people mistake for coverage, so every gap that
    is *known* is a test. A test here starting to fail is good news and means
    somebody closed a gap; it should be moved upstairs, not deleted.
    """

    def test_a_name_without_an_honorific_is_invisible(self) -> None:
        """The single largest gap. `田中と打ち合わせ` goes out."""
        assert not found("田中と打ち合わせの予定です")

    def test_an_english_name_is_invisible(self) -> None:
        assert not found("Dear Jane Doe, thanks for your note.")

    def test_a_company_name_is_invisible(self) -> None:
        assert not found("株式会社さくら商事の件です")

    def test_an_address_is_invisible(self) -> None:
        assert not found("東京都渋谷区神南一丁目の物件について")

    def test_a_short_structured_key_from_an_unlisted_vendor_is_invisible(self) -> None:
        """Entropy cannot reach it -- 4.5 bits is unreachable under 23
        characters -- and its prefix is not in the list. This is precisely the
        hole the vendor list is permanently one edit behind."""
        assert not found("key: ZZQ7-4412-BBTX")

    def test_chinese_gets_nothing_at_all(self) -> None:
        assert not found("请联系张伟先生确认合同细节")


class TestItDoesNotFireOnOrdinaryText:
    """Over-detection is the safe direction, and it is not free.

    A scanner that finds something in every prompt removes the external route
    permanently, and a router with one reachable destination is not routing.
    These are the ADR-0007 traps: text that looks sensitive and is not.
    """

    @pytest.mark.parametrize(
        "text",
        [
            "this prompt is entirely harmless, please summarise it",
            "see https://docs.example.com/guides/getting-started for details",
            "the file is at src/iriguchi/infrastructure/scanners/fallback.py",
            "この記事を日本語に翻訳してください",
            '次の JSON を整形してください: {"a": 1, "b": [2, 3]}',
            "internationalization is a long word",
            "commit 2026-08-30 に更新しました",
        ],
    )
    def test_nothing_is_found(self, text: str) -> None:
        assert not found(text), f"over-detected on {text!r}: {found(text)}"


class TestOffsetsUnderContraction:
    """What the port contract said an adapter has to check for itself.

    `tests/contracts.py` can only bounds-check, which catches normalization that
    expands and is blind to normalization that contracts -- a wrong span is
    still in bounds. The only thing that catches a contraction is asserting on
    the characters under the span, and only this file knows what they should be.
    """

    #: `e` + U+0301 twice over, so any composing normalizer shifts by two.
    #: Escapes rather than literals: the forms are indistinguishable on screen.
    PREFIX = "cafe\u0301 cafe\u0301 "

    def test_a_finding_after_two_combining_marks_still_points_at_it(self) -> None:
        text = self.PREFIX + "tanaka@example.com"
        assert ("email-shape", "tanaka@example.com") in found(text)

    def test_and_after_an_expansion_too(self) -> None:
        text = "㍿ ㍿ " + "tanaka@example.com"
        assert ("email-shape", "tanaka@example.com") in found(text)

    def test_and_with_both_in_the_same_text(self) -> None:
        text = self.PREFIX + "㍿ " + "password: hunter2sekret"
        assert ("credential-context", "hunter2sekret") in found(text)


class TestThroughTheDomain:
    """The only thing the router actually asks of it."""

    def test_a_prompt_with_a_finding_is_restricted(self) -> None:
        findings = FallbackScanner().scan("send it to tanaka@example.com")
        assert Sensitivity.from_findings(findings).level is SensitivityLevel.RESTRICTED

    def test_a_prompt_without_one_is_clear(self) -> None:
        findings = FallbackScanner().scan("please summarise the attached article")
        assert Sensitivity.from_findings(findings).level is SensitivityLevel.CLEAR


class TestTheJapaneseSeparator:
    """Both halves of a change the evaluation corpus asked for.

    The rule originally required `:` or `=`. Japanese writes
    `パスワードは hunter2 です`, never `パスワード: hunter2`, so the rule was
    blind to the language half this project's users write in — and the corpus
    found it, which is the corpus doing its job.

    Adding `は` and `が` cost precision immediately: `パスワードは変更しました`
    became a finding. A rule that fires on every sentence mentioning a password
    makes the external route unreachable, which is a different failure from
    being cautious — the same argument as the honorific stoplist.
    """

    def test_a_topic_particle_separates_a_password_from_its_value(self) -> None:
        assert ("credential-context", "hunter2sekret") in found("パスワードは hunter2sekret です")

    def test_a_sentence_about_a_password_is_not_a_password(self) -> None:
        assert "credential-context" not in rules(
            "パスワードは変更しましたので、再度お試しください。"
        )

    def test_the_ascii_separator_still_works(self) -> None:
        assert ("credential-context", "hunter2sekret") in found("password: hunter2sekret")

    def test_what_the_tightening_costs(self) -> None:
        """A passphrase written in kana is invisible to this rule.

        Stated as a test rather than a comment, so that closing the gap is
        visible as this test starting to fail. Rare, and it is what mamori is
        for.
        """
        assert "credential-context" not in rules("パスワードはひみつのあいことばです")
