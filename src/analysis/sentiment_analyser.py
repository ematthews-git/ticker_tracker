from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import re
import logging

from models import SentimentCategory

logger = logging.getLogger(__name__)


class SentimentAnalyser:
    """Analyses sentiment of Reddit posts/comments"""

    def __init__(self):
        self.analyser = SentimentIntensityAnalyzer()

        # {word: score}, -4 to 4
        lexicon = {
            # Bullish terms
            "moon": 3.5,
            "mooning": 3.5,
            "rocket": 3.0,
            "rockets": 3.0,
            "bullish": 3.0,
            "breakout": 2.5,
            "squeeze": 2.5,
            "gamma": 2.0,
            "calls": 1.5,
            "buy": 2.0,
            "long": 1.5,
            "undervalued": 2.5,
            "gains": 2.5,
            "tendies": 3.0,
            "diamond": 2.0,
            "hold": 1.5,
            "hodl": 2.0,
            "accumulate": 2.0,
            "catalyst": 2.0,
            "rally": 2.5,
            "bounce": 1.5,
            "support": 1.0,
            # Bearish terms
            "bearish": -3.0,
            "crash": -3.5,
            "dump": -3.0,
            "dumping": -3.0,
            "rug": -4.0,
            "rugpull": -4.0,
            "overvalued": -2.5,
            "puts": -1.5,
            "sell": -2.0,
            "bag": -2.5,
            "bags": -2.5,
            "bagholder": -2.0,
            "bagholding": -2.0,
            "loss": -2.5,
            "losses": -2.5,
            "red": -1.5,
            "resistance": -1.0,
            "dilution": -2.5,
            "scam": -4.0,
            "fomo": -1.5,
            # Neutral/context terms
            "dd": 0.5,  # Due diligence - slightly positive
            "dip": 0.0,  # Can be positive (buying opportunity) or negative
            "yolo": 0.0,  # Neutral, just risky
        }

        # Update VADER with lexicon
        self.analyser.lexicon.update(lexicon)

        # Multi-word phrases.
        self.phrase_lexicon = {
            # Bullish phrases
            "to the moon": 3.5,
            "gap up": 2.5,
            "break out": 2.5,
            "all in": 2.0,
            "print money": 3.0,
            "free money": 2.5,
            "easy money": 2.0,
            "buy the dip": 2.5,
            "loading up": 2.0,
            "sending it": 2.5,
            "short squeeze": 3.0,
            "diamond hands": 2.5,
            "lets go": 2.0,
            "lfg": 2.0,
            # Bearish phrases
            "paper hands": -2.5,
            "weak hands": -2.5,
            "bag holder": -2.5,
            "bag holding": -2.5,
            "off a cliff": -3.0,
            "gap down": -2.5,
            "dead cat": -2.5,
            "catch a falling knife": -3.0,
            "heading to zero": -3.5,
            "pump and dump": -3.0,
            "exit liquidity": -3.0,
            "shorting this": -1.5,
            "rug pull": -4.0,
            "stay away": -2.5,
            "dont buy": -2.5,
        }

        # Register the joined-token form in VADER so the compound score picks it up.
        self.analyser.lexicon.update(
            {
                phrase.replace(" ", "_"): score
                for phrase, score in self.phrase_lexicon.items()
            }
        )

        # Compile a single regex that matches any phrase
        sorted_phrases = sorted(self.phrase_lexicon.keys(), key=len, reverse=True)
        self._phrase_pattern = re.compile(
            r"\b(" + "|".join(re.escape(p) for p in sorted_phrases) + r")\b",
            re.IGNORECASE,
        )

        # Emoji → sentiment. VADER's tokenizer drops single-codepoint tokens,
        # so we map each emoji to a multi-character placeholder word and score
        # that placeholder in the lexicon. Normalisation replaces the emoji
        # with " <placeholder> " so it tokenises cleanly.
        self.emoji_lexicon = {
            # Bullish
            "🚀": ("emj_rocket", 2.5),
            "📈": ("emj_chartup", 2.0),
            "🐂": ("emj_bull", 2.0),
            "💎": ("emj_diamond", 1.5),
            "🙌": ("emj_hands", 1.0),
            "🔥": ("emj_fire", 1.0),
            "🤑": ("emj_moneyface", 2.0),
            "🌙": ("emj_crescent", 2.0),
            # Bearish
            "📉": ("emj_chartdown", -2.0),
            "🐻": ("emj_bear", -2.0),
            "💩": ("emj_poop", -2.5),
            "🤡": ("emj_clown", -1.5),
            "🩸": ("emj_blood", -2.0),
            "⚰️": ("emj_coffin", -2.5),
        }
        self.analyser.lexicon.update(
            {token: score for token, score in self.emoji_lexicon.values()}
        )
        # Regex that finds any of the registered emojis so we can swap them
        # for their placeholder tokens.
        sorted_emojis = sorted(self.emoji_lexicon.keys(), key=len, reverse=True)
        self._emoji_pattern = re.compile(
            "(" + "|".join(re.escape(e) for e in sorted_emojis) + ")"
        )
        self._emoji_token_map = {
            emj: token for emj, (token, _) in self.emoji_lexicon.items()
        }

        self.bull_patterns = {
            r"to\s+the\s+moon",
            r"🚀+",
            r"💎+\s*🙌+",
            r"lets?\s+go+",
            r"lfg",
        }

        self.bear_patterns = [
            r"rug\s*pull",
            r"stay\s+away",
            r"avoid",
            r"don\'?t\s+buy",
        ]

        # Conditional / hypothetical markers. Presence dampens score magnitude
        # because the author is speculating, not asserting.
        self._modality_pattern = re.compile(
            r"\b(if|could|might|would|should|maybe|perhaps|hopefully|assuming|suppose|potentially)\b",
            re.IGNORECASE,
        )

        # Sarcasm markers. Used only to dampen as sarcasm detection confidence is low
        self._sarcasm_patterns = [
            re.compile(r"/s\b", re.IGNORECASE),
            re.compile(r"\byeah[,\s]+right\b", re.IGNORECASE),
            re.compile(r"\bsure[,\s]+buddy\b", re.IGNORECASE),
            re.compile(r"\btotally\s+not\b", re.IGNORECASE),
            re.compile(r"\bwhat\s+could\s+go\s+wrong\b", re.IGNORECASE),
            re.compile(r"\bthis\s+is\s+fine\b", re.IGNORECASE),
            re.compile(r"\brolls?\s+eyes\b", re.IGNORECASE),
            # Bullish word in quotes, e.g. a "genius" play / "moon" stock
            re.compile(r'"\s*(moon|genius|guaranteed|safe|easy)\s*"', re.IGNORECASE),
        ]

    def _apply_pattern_boost(self, text: str, base_score: float) -> float:
        """Apply sentiment boosts based on pattern matching.

        Args:
            text (str): The text to analyse.
            base_score (float): The base original score.

        Returns:
            float: Updated sentiment score
        """
        text_lower = text.lower()
        boost = 0.0

        # check bulls
        for pattern in self.bull_patterns:
            if re.search(pattern, text_lower):
                boost += 0.2

        # check bears
        for pattern in self.bear_patterns:
            if re.search(pattern, text_lower):
                boost -= 0.2

        updated = base_score + boost
        # clamps between -1 and 1
        return max(-1.0, min(1.0, updated))

    def _normalise_text(self, text: str) -> str:
        """Clean text for analyis.

        Args:
            text (str): Raw text from post/comment

        Returns:
            str: Cleaned text
        """
        # Remove markdown formatting
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
        # remove any urls
        text = re.sub(r"(https?://\S+|www\.\S+|\b\w+\.\w{2,}\S*)", "", text)

        text = self._emoji_pattern.sub(
            lambda m: " " + self._emoji_token_map[m.group(0)] + " ", text
        )

        text = self._phrase_pattern.sub(
            lambda m: m.group(0).lower().replace(" ", "_"), text
        )
        # Remove excessive whitespace
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def _apply_modality_dampening(self, text: str, score: float) -> float:
        """Halve sentiment magnitude when the text is dominated by conditional
        / hypothetical language ("if it moons", "could crash"). The author is
        speculating rather than asserting, so the signal is weaker."""
        if score == 0.0:
            return score
        matches = self._modality_pattern.findall(text)
        if not matches:
            return score
        word_count = max(1, len(text.split()))

        if len(matches) >= 2 or (len(matches) >= 1 and word_count < 15):
            return score * 0.5
        return score

    def _apply_sarcasm_dampening(self, text: str, score: float) -> float:
        """Halve magnitude when sarcasm markers are present."""
        if score == 0.0:
            return score
        for pat in self._sarcasm_patterns:
            if pat.search(text):
                return score * 0.5
        # Clown emoji next to bullish language is a strong sarcasm signal.
        if "🤡" in text and score > 0:
            return score * 0.5
        return score

    def _apply_question_dampening(self, text: str, score: float) -> float:
        """Questions carry weaker signal than declarative statements. If most
        sentences are questions, dampen by 0.7."""
        if score == 0.0:
            return score
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        sentences = [s for s in sentences if s]
        if not sentences:
            return score
        question_count = sum(1 for s in sentences if s.rstrip().endswith("?"))
        if question_count / len(sentences) > 0.5:
            return score * 0.7
        return score

    def analyse_text(self, text: str) -> float:
        """Analyses sentiment of a text.

        Args:
            text (str): Text to analyse

        Returns:
            float: Sentiment score betweeen -1 and 1
        """
        if not text or not text.strip():
            return 0.0

        # Clean text (also does phrase + emoji substitution)
        cleaned_text = self._normalise_text(text)

        # Get score from VADER
        scores = self.analyser.polarity_scores(cleaned_text)

        # Use compound score (between -1 and 1)
        score = scores["compound"]

        # Apply pattern adjustments
        score = self._apply_pattern_boost(cleaned_text, score)

        # Modality / sarcasm / question dampening (all act on the original text
        # so markers aren't lost after phrase substitution).
        score = self._apply_modality_dampening(text, score)
        score = self._apply_sarcasm_dampening(text, score)
        score = self._apply_question_dampening(text, score)

        # Clamp again after dampening chain (dampening can't exceed bounds,
        # but be defensive).
        score = max(-1.0, min(1.0, score))

        return round(score, 4)

    def analyse_batch(self, texts: list[str]) -> list[float]:
        """Analyses sentiment of a list of texts.

        Args:
            texts (list[str]): List of texts to analyse

        Returns:
            list[float]: List of sentiment scores
        """
        return [self.analyse_text(text) for text in texts]

    def categorise_sentiment(self, score: float) -> SentimentCategory:
        """Categorise a sentiment score into a label.

        Args:
            score (float): Sentiment score between -1 and 1.

        Returns:
            SentimentCategory: The appropriate category.
        """
        if score >= 0.5:
            return SentimentCategory.VERY_POSITIVE
        elif score >= 0.1:
            return SentimentCategory.POSITIVE
        elif score >= -0.1:
            return SentimentCategory.NEUTRAL
        elif score >= -0.5:
            return SentimentCategory.NEGATIVE
        else:
            return SentimentCategory.VERY_NEGATIVE
