"""
text_analyzer.py
Module 3: Content Analysis & Semantic "Brain" Layer
Advanced NLP pipeline utilizing spaCy, YAKE, KeyBERT, and Sumy.
"""

from collections import Counter
import re
from typing import Any, Dict, List, Optional

# 1. Linguistic Parsing & Named Entity Recognition (spaCy)
try:
    import spacy

    nlp = spacy.load("en_core_web_sm")
except Exception:
    nlp = None

# 2. Keyphrase Extraction (YAKE)
try:
    import yake
except ImportError:
    yake = None

# 3. Semantic Keyword Extraction (KeyBERT)
try:
    from keybert import KeyBERT

    kw_model = KeyBERT()
except Exception:
    kw_model = None

# 4. Extractive Summarization (Sumy)
try:
    import nltk
    from sumy.nlp.tokenizers import Tokenizer
    from sumy.parsers.plaintext import PlaintextParser
    from sumy.summarizers.lsa import LsaSummarizer

    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        nltk.download("punkt", quiet=True)
except ImportError:
    PlaintextParser = None


class TextAnalyzer:

    def __init__(self, custom_stop_words: Optional[List[str]] = None):
        """Initializes the multi-model text analysis engine."""
        self.stop_words = set(
            custom_stop_words
            or [
                "the",
                "and",
                "to",
                "of",
                "a",
                "in",
                "for",
                "is",
                "on",
                "that",
                "by",
                "this",
                "with",
                "it",
                "not",
                "or",
                "be",
                "are",
                "from",
                "at",
                "as",
                "page",
                "section",
                "table",
                "figure",
                "shall",
                "must",
                "may",
                "can",
            ]
        )

        if yake:
            self.yake_extractor = yake.KeywordExtractor(
                lan="en", n=3, dedupLim=0.8, top=10
            )
        else:
            self.yake_extractor = None

    def analyze_page(self, text_blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Runs multi-stage NLP analysis across page text blocks."""
        full_text = " ".join(
            [
                b.get("text_content", "")
                for b in text_blocks
                if b.get("text_content")
            ]
        ).strip()

        if not full_text:
            return {
                "page_topics": [],
                "key_concepts": [],
                "named_entities": [],
                "intent_category": "empty",
                "page_summary": "Blank or non-textual page.",
                "word_frequencies": {},
            }

        # Step 1: Named Entity Recognition & Linguistic Filtering via spaCy
        entities = []
        spacy_keywords = []
        if nlp:
            doc = nlp(full_text)
            entities = list(
                set([ent.text for ent in doc.ents if len(ent.text) > 2])
            )
            spacy_keywords = [
                token.lemma_.lower()
                for token in doc
                if token.pos_ in ["NOUN", "PROPN"]
                and not token.is_stop
                and len(token.text) > 2
            ]

        # Step 2: Extract Keyphrases using YAKE & KeyBERT
        keyphrases = self._extract_keyphrases(full_text)

        words = (
            spacy_keywords
            if spacy_keywords
            else re.findall(r"\b[A-Za-z]{3,}\b", full_text.lower())
        )
        filtered_words = [w for w in words if w not in self.stop_words]
        word_counts = Counter(filtered_words)

        combined_concepts = list(
            dict.fromkeys(
                keyphrases + [w for w, _ in word_counts.most_common(5)]
            )
        )

        # Step 3: Extractive Summarization
        summary = self._summarize_text(full_text, combined_concepts)

        # Step 4: Intent Classification
        intent = self._classify_intent(full_text)

        return {
            "page_topics": combined_concepts[:5],
            "key_concepts": combined_concepts,
            "named_entities": entities,
            "intent_category": intent,
            "page_summary": summary,
            "word_frequencies": dict(word_counts.most_common(10)),
        }

    def _extract_keyphrases(self, text: str) -> List[str]:
        """Combines KeyBERT and YAKE for multi-word phrase extraction."""
        extracted = []

        if kw_model:
            try:
                kb_res = kw_model.extract_keywords(
                    text,
                    keyphrase_ngram_range=(1, 3),
                    stop_words="english",
                    top_n=5,
                )
                extracted.extend([kw for kw, score in kb_res])
            except Exception:
                pass

        if self.yake_extractor:
            try:
                yake_res = self.yake_extractor.extract_keywords(text)
                yake_sorted = sorted(yake_res, key=lambda x: x[1])
                extracted.extend([kw for kw, score in yake_sorted[:5]])
            except Exception:
                pass

        return list(dict.fromkeys(extracted))

    def _summarize_text(self, text: str, fallback_concepts: List[str]) -> str:
        """Generates extractive summary using Sumy."""
        if PlaintextParser:
            try:
                parser = PlaintextParser.from_string(text, Tokenizer("english"))
                summarizer = LsaSummarizer()
                summary_sentences = summarizer(parser.document, 2)
                res = " ".join([str(s) for s in summary_sentences]).strip()
                if res:
                    return res
            except Exception:
                pass

        concepts = (
            ", ".join(fallback_concepts[:3])
            if fallback_concepts
            else "technical specifications"
        )
        return f"Page details technical documentation regarding {concepts}."

    def _classify_intent(self, text: str) -> str:
        """Classifies page functional intent."""
        t = text.lower()
        if any(
            k in t for k in ["error", "troubleshoot", "fail", "exception", "fault"]
        ):
            return "troubleshooting"
        elif any(
            k in t for k in ["definition", "glossary", "abbreviation", "acronym"]
        ):
            return "glossary"
        elif any(
            k in t for k in ["overview", "introduction", "scope", "purpose"]
        ):
            return "overview"
        elif any(
            k in t for k in ["command", "apdu", "tlv", "tag", "format", "byte"]
        ):
            return "specification"
        return "general_content"
