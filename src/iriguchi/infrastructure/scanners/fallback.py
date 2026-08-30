"""The built-in scanner. Deliberately dumb, and wrong in one direction only.

ADR-0005: iriguchi does not grow a second, worse PII detector. mamori has
language packs in three languages, a measured corpus and thirty-one ADRs of
reasoning about this exact problem, and it is the adapter you want. This exists
so that iriguchi *works* without it, and the way it works without it is by
over-detecting.

**Every rule here is allowed to be wrong in exactly one direction.** A false
positive routes a prompt to the local model when it could safely have left: the
person gets a worse answer and says so. A false negative sends something out
that should have stayed: nothing says anything, and the text is on somebody
else's disk. Those are not comparable, so every threshold in this file is set
toward the first.

That is why `long-digit-run` fires on order numbers and why the honorific rule
fires on `お母さん`. Both are named in their own comments, because mamori's rule
for a detector rule is that it says which way it leans and what it also catches
-- and this scanner has more to admit than most.

**What it does not do at all**, so that nobody mistakes its silence for
coverage: it does not find names without an honorific, addresses, company names,
account numbers by checksum, dates of birth, or anything at all in Chinese. Those
are what installing mamori is for.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from ...domain.sensitivity import Finding
from ..normalization import normalize
from .entropy import looks_random

__all__ = ["FallbackScanner"]


@dataclass(frozen=True, slots=True)
class _Rule:
    """One pattern, and which part of it is the sensitive half."""

    id: str
    pattern: re.Pattern[str]
    #: Which capture group holds the value. `0` is the whole match. Used where
    #: the anchor is not itself sensitive: `password: hunter2` should point at
    #: `hunter2`, not at the word `password`.
    group: int = 0


#: Honorifics that follow something other than a name. Never complete, and it
#: does not have to be: everything it misses is an over-detection, which routes
#: local. It exists because `お母さん` and `皆さん` appear in almost every
#: Japanese prompt, and a scanner that flags a finding in all of them makes the
#: external route unreachable in practice -- which is a different failure from
#: being cautious.
_NOT_NAMES: frozenset[str] = frozenset(
    {
        "皆さん",
        "みなさん",
        "皆様",
        "みなさま",
        "お客様",
        "おきゃくさま",
        "お母さん",
        "お父さん",
        "お兄さん",
        "お姉さん",
        "おじさん",
        "おばさん",
        "母さん",
        "父さん",
        "兄さん",
        "姉さん",
        "奥さん",
        "旦那さん",
        "神様",
        "王様",
        "お疲れ様",
        "ご苦労様",
        "お嬢さん",
        "おまわりさん",
        "どちら様",
        "何様",
        "そちら様",
        "お互い様",
        "ご主人様",
        "お坊さん",
    }
)

_RULES: tuple[_Rule, ...] = (
    # Leans recall. Deliberately looser than a real address grammar: a
    # single-label domain and a two-character TLD both match, because the cost
    # of matching `a@b.co` that is not an address is a local route.
    _Rule(
        "fallback.email-shape",
        re.compile(r"[\w.%+\-]+@[\w\-]+(?:\.[\w\-]+)+"),
    ),
    # Very high precision. A PEM header is not something that appears by
    # accident, and the whole block is worth pointing at rather than the header.
    _Rule(
        "fallback.private-key-block",
        re.compile(r"-----BEGIN[ A-Z]*PRIVATE KEY-----"),
    ),
    # The half entropy cannot reach. `AKIAIOSFODNN7EXAMPLE` scores 3.68 bits --
    # below a URL path -- so no threshold catches it and its prefix has to.
    # High precision; the cost is that the list is only ever as current as the
    # last person to edit it, and a vendor not named here is invisible to this
    # rule.
    _Rule(
        "fallback.vendor-key-prefix",
        re.compile(
            r"(?:sk-[A-Za-z0-9\-_]{8,}"
            r"|gh[pousr]_[A-Za-z0-9]{16,}"
            r"|github_pat_[A-Za-z0-9_]{20,}"
            r"|AKIA[0-9A-Z]{12,}"
            r"|xox[baprs]-[A-Za-z0-9\-]{8,}"
            r"|AIza[0-9A-Za-z\-_]{20,}"
            r"|ya29\.[0-9A-Za-z\-_]{10,}"
            r"|glpat-[0-9A-Za-z\-_]{16,}"
            r"|npm_[A-Za-z0-9]{20,})"
        ),
    ),
    # `https://user:hunter2@internal.example.com`. The credentials are the
    # finding, not the host, so the group is the pair.
    _Rule(
        "fallback.url-credentials",
        re.compile(r"://([^\s/:@]+:[^\s/@]+)@"),
        group=1,
    ),
    # The anchor is not the secret. `password: hunter2` points at `hunter2`,
    # because redacting the word `password` protects nothing and makes the
    # explanation nonsense. Leans recall on the value: anything up to
    # whitespace counts, so `password: <see attached>` is a finding too.
    _Rule(
        "fallback.credential-context",
        re.compile(
            r"(?i:password|passwd|secret|token|api[_\- ]?key|access[_\- ]?key"
            r"|パスワード|秘密鍵|アクセスキー)"
            r"\s*[:=]\s*"
            r"(\S{3,})"
        ),
        group=1,
    ),
    # **The most over-detecting rule here, and knowingly so.** Eight or more
    # digits is a phone number, a card number and a My Number -- and also every
    # order number, invoice number, epoch timestamp and row id anybody pastes.
    # It stays because the alternative is a checksum-aware rule set, which is
    # mamori's job, and because the entropy rule cannot help: ten symbols cap a
    # digit string at 3.32 bits, so no threshold separates a card number from a
    # part number.
    #
    # No `\b`. Kanji are word characters, so `番号123456789012です` never fires
    # with one -- mamori's rule, learned the expensive way.
    _Rule(
        "fallback.long-digit-run",
        re.compile(r"(?<![0-9])[0-9]{8,}(?![0-9])"),
    ),
    # Japanese names, anchored on an honorific.
    #
    # **The run is lazy, and that is not a style choice.** Greedy, `{1,6}` walks
    # straight through the stoplist: in `皆さんお疲れ様です` it matches
    # `皆さんお疲れ様`, which is not `皆さん` and not `お疲れ様`, so neither entry
    # fires and the stoplist silently protects nothing. Lazy takes the shortest
    # run that reaches an honorific, which is the one the stoplist is written
    # against.
    #
    # It still leans recall twice over. `営業部長田中さん` reports the whole run
    # rather than the name inside it, because nothing here knows where a title
    # ends -- and the stoplist is permanently incomplete. Both errors route
    # local.
    #
    # It finds nothing without an honorific. `田中と打ち合わせ` is invisible to
    # this scanner, and that is the single largest gap in it.
    _Rule(
        "fallback.japanese-honorific",
        re.compile(r"([一-鿿゠-ヿ぀-ゟー]{1,6}?)(?:さん|様|氏|くん|君|ちゃん)"),
    ),
)

#: What counts as one token for the entropy rule. Splitting on whitespace alone
#: would hand it whole sentences; splitting on every non-alphanumeric would tear
#: `sk-live-...` into three harmless pieces. This keeps the characters that
#: appear inside keys and drops the ones that surround them.
_TOKEN = re.compile(r"[A-Za-z0-9+/=_\-]{8,}")


class FallbackScanner:
    """The scanner iriguchi ships with. Install mamori for a better one."""

    name = "fallback"

    def scan(self, text: str) -> Sequence[Finding]:
        """Everything this thinks is sensitive, at offsets into `text`.

        Matching happens on NFKC-folded text -- `ｔａｎａｋａ＠ｅｘａｍｐｌｅ．ｃｏｍ`
        is an address and missing it would send the prompt out -- and every span
        is mapped back before it is returned.

        Findings may overlap, and often do: a key inside a `password:` line is
        found by three rules. Nothing resolves them, because a route is removed
        by the first finding and cannot be removed twice.
        """
        if not text:
            return ()

        normalized = normalize(text)
        findings: list[Finding] = []

        for rule in _RULES:
            for match in rule.pattern.finditer(normalized.text):
                if rule.id == "fallback.japanese-honorific" and match.group(0) in _NOT_NAMES:
                    continue
                findings.append(
                    Finding(rule.id, self.name, normalized.to_original(*match.span(rule.group)))
                )

        for match in _TOKEN.finditer(normalized.text):
            if looks_random(match.group(0)):
                findings.append(
                    Finding(
                        "fallback.high-entropy-token",
                        self.name,
                        normalized.to_original(*match.span()),
                    )
                )

        # Sorted so the same text always produces the same sequence. The rules
        # run in a fixed order already, but the entropy pass runs after all of
        # them, and a caller reading an explanation wants position order.
        findings.sort(key=lambda finding: (finding.span, finding.rule))
        return tuple(findings)
