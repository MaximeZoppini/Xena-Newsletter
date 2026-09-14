import json
import logging
from typing import Dict, Any, Optional
from config import GEMINI_API_KEY, MIN_INTEREST_SCORE

logger = logging.getLogger("analyzer")

SYSTEM_PROMPT = """Tu es un analyste de presse indépendant, fact-checker et rédacteur de synthèse ultra-rigoureux.
Ta mission est d'analyser les dépêches et révélations issues de médias indépendants, de la tech et des marchés de prédiction pour en extraire le fait vérifiable pur, sans biais sensationnaliste ni orientation partisane.

Pour chaque actualité soumise :
1. "factual_core" : Résume le FAIT BRUT avéré en 1 ou 2 phrases concises. Zéro jargon, zéro adjectif superflu.
2. "framing_bias" : Identifie en 1 phrase courte le cadrage ou l'angle politique/éditorial de la source (ex: "Angle critique des institutions / Mediapart", "Prise de position pro-privacy / 404 Media", "Pure probabilité de marché / Polymarket").
3. "interest_score" : Note de 1 à 10 de l'intérêt et de la nouveauté de l'information pour le grand public / tech (1 = banal ou redite, 7 = vrai fait d'actualité ou tech pertinent, 9-10 = révélation majeure).
4. "tweet_text" : Rédige le tweet final prêt à être posté sur X.
   - Longueur STRICTE : maximum 250 caractères (hors URL).
   - Style : percutant, objectif, sobre, direct, avec 1 emoji au début.
   - Mentionne la source ou la probabilité si Polymarket.
   - Ne mets PAS de hashtags agressifs (#breaking, #scandale).

Réponds UNIQUEMENT sous forme d'un objet JSON strict valide avec les clés :
{
  "factual_core": "...",
  "framing_bias": "...",
  "interest_score": 8,
  "tweet_text": "..."
}
"""

class NewsAnalyzer:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or GEMINI_API_KEY
        self.client = None
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Erreur initialisation Google GenAI Client: {e}")

    def analyze(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.client:
            logger.warning("Pas de clé GEMINI_API_KEY configurée. Analyse simulée en mode mock.")
            return {
                "factual_core": f"Fait brut extrait de : {item['title']}",
                "framing_bias": f"Source : {item['source']} ({item.get('known_bias', 'Non spécifié')})",
                "interest_score": 8,
                "tweet_text": f"💡 {item['title'][:180]}\n\n🔗 {item['url']}"
            }

        user_content = f"""
SOURCE : {item['source']} (Contexte éditorial : {item.get('known_bias', 'Non précisé')})
TITRE : {item['title']}
URL : {item['url']}
CONTENU/RÉSUMÉ :
{item.get('summary', '')}
"""
        try:
            from google.genai import types
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.2
                )
            )
            raw_text = response.text.strip()
            # Nettoyage markdown éventuel
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]

            data = json.loads(raw_text.strip())
            # Ajouter l'URL à la fin du tweet si elle n'y est pas
            tweet = data.get("tweet_text", "")
            if item['url'] not in tweet:
                tweet = f"{tweet}\n\n🔗 {item['url']}"
            data["tweet_text"] = tweet

            return data
        except Exception as e:
            logger.error(f"Erreur lors de l'analyse Gemini de '{item['title']}': {e}")
            return None
