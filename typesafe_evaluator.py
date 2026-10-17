import logging
import requests
from typing import Dict, Any, Optional
from config import TYPESAFE_API_KEY, TYPESAFE_MODEL

logger = logging.getLogger("typesafe_evaluator")

class TypeSafeEvaluator:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or TYPESAFE_API_KEY
        self.model = model or TYPESAFE_MODEL or "jev-latest"
        self.endpoint = "https://api.typesafe.ai/v1/systemone"

    def is_available(self) -> bool:
        return bool(self.api_key)

    def evaluate(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Évalue un article avec Jev (System One) pour filtrer rapidement le bruit
        et quantifier l'impartialité et l'impact systémique en quelques millisecondes.
        """
        if not self.is_available():
            return {"should_analyze": True, "reason": "TypeSafe désactivé (pas de clé API)"}

        title = item.get("title", "").strip()
        summary = item.get("summary", "").strip()
        source = item.get("source", "").strip()

        state = f"Source: {source}\nTitle: {title}\nSummary: {summary[:1000]}"

        payload = {
            "model": self.model,
            "state": state,
            "questions": {
                "is_investigation_or_scoop": {
                    "type": "noul",
                    "instructions": "Is this a genuinely significant development in one of these three areas only: (1) major geopolitics (wars, ceasefires, sanctions, international agreements, power shifts between nations), (2) technological or scientific breakthroughs (quantum, frontier AI, revolutionary robots, autonomous vehicles or vehicles with unprecedented capabilities unveiled live such as a new Tesla, historic space missions, published discoveries), (3) major business moves (mega-mergers, central bank decisions, trade wars, industry-reshaping deals)? Answer no for conventional new car models (e.g. a new SUV, even powerful or electric), gadgets, routine politics, culture, sports, lifestyle or local news."
                },
                "is_opinion_or_pr": {
                    "type": "noul",
                    "instructions": "Is this primarily an opinion column, partisan rant, sponsored content, deal/promo, buying guide, hands-on product review, lifestyle, culture or sports piece?"
                },
                "systemic_importance": {
                    "type": "score",
                    "instructions": "Rate the systemic impact and societal or technical gravity of this development.",
                    "criteria": [
                        "Trivial, off-topic (culture, sports, lifestyle, gadgets) or routine",
                        "Minor company, political or product news",
                        "Notable geopolitical, technological or economic development",
                        "Major geopolitical event, technological breakthrough or industry-reshaping business move",
                        "Historic event that changes the world order, an industry or what is technically possible"
                    ]
                }
            }
        }

        import time
        t0 = time.perf_counter()
        try:
            resp = requests.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=5
            )
            latency_ms = int((time.perf_counter() - t0) * 1000)

            if resp.status_code != 200:
                logger.warning(f"TypeSafe API returned {resp.status_code}: {resp.text[:150]}")
                return {
                    "should_analyze": True,
                    "reason": f"Erreur API Jev ({resp.status_code}) -> fallback Gemini",
                    "latency_ms": latency_ms,
                    "tokens_in": 0,
                    "tokens_out": 0
                }

            data = resp.json()
            answers = data.get("answers", {})
            usage = data.get("usage", {})
            tokens_in = usage.get("input_tokens", 400)
            tokens_out = usage.get("output_tokens", 40)

            p_scoop = answers.get("is_investigation_or_scoop", {}).get("noul", 0.5)
            p_opinion = answers.get("is_opinion_or_pr", {}).get("noul", 0.0)
            score_data = answers.get("systemic_importance", {})
            raw_score = score_data.get("score", 1.0)  # 0.0 à 4.0
            
            # Échelle 0-10 équivalente
            scaled_score = round(raw_score * 2.5, 1)

            # Règle de filtrage Stage 1 :
            # 1. Si opinion/PR pure > 0.45 -> Rejet
            if p_opinion > 0.45:
                return {
                    "should_analyze": False,
                    "estimated_score": scaled_score,
                    "reason": f"Opinion partisane ou promotionnelle (prob: {p_opinion:.2f})",
                    "p_scoop": p_scoop,
                    "p_opinion": p_opinion,
                    "systemic_score": scaled_score,
                    "latency_ms": latency_ms,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "raw_answers": answers
                }

            # 2. Si faible en scoop (< 0.35) et impact faible à modéré (< 6.0 / 10) -> Rejet
            if p_scoop < 0.35 and scaled_score < 6.0:
                return {
                    "should_analyze": False,
                    "estimated_score": scaled_score,
                    "reason": f"Sujet mineur ou routinier (scoop prob: {p_scoop:.2f}, impact: {scaled_score}/10)",
                    "p_scoop": p_scoop,
                    "p_opinion": p_opinion,
                    "systemic_score": scaled_score,
                    "latency_ms": latency_ms,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "raw_answers": answers
                }

            # Candidat qualifié pour l'Étage 2 (Gemini)
            return {
                "should_analyze": True,
                "estimated_score": scaled_score,
                "reason": "Validé par TypeSafe Jev",
                "p_scoop": p_scoop,
                "p_opinion": p_opinion,
                "systemic_score": scaled_score,
                "latency_ms": latency_ms,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "raw_answers": answers
            }

        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.warning(f"Exception lors de l'appel TypeSafe Jev ({e}), repli automatique sur Gemini.")
            return {
                "should_analyze": True,
                "reason": f"Exception Jev ({e}) -> fallback Gemini",
                "latency_ms": latency_ms,
                "tokens_in": 0,
                "tokens_out": 0
            }
