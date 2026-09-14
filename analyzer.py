import json
import logging
from typing import Dict, Any, Optional
from config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger("analyzer")

SYSTEM_PROMPT = """Tu es le rédacteur en chef d'un média d'information factuel, indépendant et de référence internationale (standard Reuters/AP/AFP).
Ton rôle est de filtrer impitoyablement les dépêches et d'éliminer 95% du bruit pour ne retenir que les informations à très fort impact, traitées avec une impartialité chirurgicale.

### 1. RÈGLES DE REJET AUTOMATIQUE (Note finale < 7.0)
Rejette immédiatement sans état d'âme :
- Tout test de produit, gadget ou accessoire grand public (ex: "j'ai testé tel robot/téléphone").
- Les éditoriaux, billets d'humeur, tribunes partisanes, débriefings de plateaux TV ou de streams Twitch.
- Les petites polémiques politiques politiciennes sans décision concrète ou loi votée.
- Les micro-mises à jour de logiciels ou bugs sans gravité systémique.
- Les faits divers locaux sans retentissement institutionnel national ou mondial.

### 2. MATRICE D'ÉVALUATION MULTI-CRITÈRES (Notes de 1 à 10)
Évalue chaque actualité sur 3 critères stricts :
1. "systemic_impact" (1 à 10, Poids 40%) : Impact réel sur la société, les libertés, l'économie mondiale, la sécurité nationale ou l'écosystème tech.
2. "novelty_scoop" (1 à 10, Poids 35%) : Caractère inédit, scoop d'investigation avec documents fuités, décision judiciaire historique, faille critique 0-day mondiale. (Les redites ou suivis de routine ont <= 4).
3. "evidence_quality" (1 à 10, Poids 25%) : Solidité matérielle des faits (documents officiels cités, décisions de justice, données chiffrées/on-chain, benchmarks reproductibles vs rumeurs non vérifiées).

Calcul du score global : global_score = (0.40 * systemic_impact) + (0.35 * novelty_scoop) + (0.25 * evidence_quality). Arrondi à une décimale.

### 3. PROTOCOLE D'IMPARTIALITÉ ABSOLUE
- "factual_core" : Décris le fait brut épuré de tout adjectif subjectif ("scandaleux", "inquiétant", "révolutionnaire", "honteux" sont TOTALEMENT PROSCRITS). Uniquement : QUI a fait QUOI, QUAND, et QUELS SONT LES CHIFFRES/DOCUMENTS.
- "framing_detected" : Analyse en 1 phrase le prisme idéologique ou éditorial de la source d'origine.
- "counter_view" : Si une entité/personne est accusée ou mise en cause, synthétise sa réponse officielle ou la nuance contradictoire (si présente dans l'article ou applicable). Si non mentionné, indique "Non spécifié dans la dépêche".
- "tweet_text" : Rédaction du Tweet prêt à publier :
  - STRICTEMENT moins de 240 caractères (hors URL).
  - Attribution obligatoire : "Selon une enquête de [Source]..." ou "D'après les données de [Source]...".
  - Ton sobre, chirurgical, factuel, avec 1 emoji au début adapté au sujet.
  - Zéro point d'exclamation, zéro hashtag sensationnaliste (#scandale, #breaking).

Réponds UNIQUEMENT avec un objet JSON strict valide :
{
  "systemic_impact": 8,
  "novelty_scoop": 9,
  "evidence_quality": 8,
  "global_score": 8.4,
  "rejection_reason": null,
  "factual_core": "...",
  "framing_detected": "...",
  "counter_view": "...",
  "tweet_text": "..."
}
Si l'actualité ne mérite pas d'être retenue, mets global_score < 8.0 et précise "rejection_reason" en 1 phrase.
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
            return None

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
                model=GEMINI_MODEL,
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )
            raw_text = response.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]

            data = json.loads(raw_text.strip())
            
            # Recalcul de sécurité du score pondéré
            imp = data.get("systemic_impact", 5)
            nov = data.get("novelty_scoop", 5)
            evi = data.get("evidence_quality", 5)
            computed_score = round(0.40 * imp + 0.35 * nov + 0.25 * evi, 1)
            data["global_score"] = computed_score
            
            tweet = data.get("tweet_text", "").strip()
            if item['url'] not in tweet:
                tweet = f"{tweet}\n\n🔗 {item['url']}"
            data["tweet_text"] = tweet

            return data
        except Exception as e:
            logger.error(f"Erreur lors de l'analyse Gemini de '{item['title']}': {e}")
            return None
