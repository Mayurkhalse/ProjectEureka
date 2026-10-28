"""Deterministic Multilingual Notice Texts.

Strictly deterministic notices for policy denials, clarifications, data quality banners,
and system errors. LLMs are never permitted to generate or embellish these notices.
"""

from typing import Dict, Literal

Language = Literal["en", "mr", "hi"]

NOTICES: Dict[str, Dict[str, str]] = {
    "unavailable": {
        "en": "Not available for your access level: {labels}.",
        "mr": "तुमच्या प्रवेश स्तरासाठी उपलब्ध नाही: {labels}.",
        "hi": "आपके पहुँच स्तर के लिए उपलब्ध नहीं: {labels}।",
    },
    "source_missing": {
        "en": "Data source not configured: {labels}.",
        "mr": "डेटा स्रोत उपलब्ध नाही: {labels}.",
        "hi": "डेटा स्रोत उपलब्ध नहीं: {labels}।",
    },
    "clarify_compare": {
        "en": "Which districts should I compare? Please name at least two.",
        "mr": "तुलना करण्यासाठी किमान दोन जिल्ह्यांची नावे सांगा.",
        "hi": "तुलना के लिए कम से कम दो जिलों के नाम बताइए।",
    },
    "synthetic": {
        "en": "Illustrative data, not from a live source.",
        "mr": "उदाहरणार्थ आकडेवारी, थेट स्रोतावरून नाही.",
        "hi": "उदाहरण डेटा, लाइव स्रोत से नहीं।",
    },
    "heuristic": {
        "en": "Estimated by a rule of thumb, not a trained model.",
        "mr": "अंदाजे आकडेवारी, प्रशिक्षित मॉडेलवरून नाही.",
        "hi": "अनुमानित डेटा, प्रशिक्षित मॉडल से नहीं।",
    },
    "seed": {
        "en": "Offline reference data, not live.",
        "mr": "ऑफलाइन संदर्भ माहिती, थेट नाही.",
        "hi": "ऑफ़लाइन संदर्भ डेटा, लाइव नहीं।",
    },
    "unreadable": {
        "en": "I could not work out what to look up. Try: 'crisis and sentiment of Dhule'.",
        "mr": "काय शोधायचे ते समजले नाही. उदा. 'धुळे संकट आणि भावना'.",
        "hi": "समझ नहीं आया। उदाहरण: 'धुले संकट और भावना'।",
    },
    "unrecognized_query": {
        "en": "I could not understand what to look up. Try asking about district sentiment or crisis SLA, e.g. 'crisis and sentiment of Dhule', or 'compare Pune and Thane'.",
        "mr": "काय शोधायचे ते समजले नाही. जिल्ह्याची जनभावना किंवा संकट SLA बद्दल विचारा, उदा. 'धुळे संकट आणि भावना' किंवा 'पुणे आणि ठाणे तुलना'.",
        "hi": "समझ नहीं आया। जिले की जनभावना या संकट SLA के बारे में पूछें, जैसे 'धुले संकट और भावना', या 'पुणे और ठाणे की तुलना'।",
    },
    "timeout": {
        "en": "Operation timed out before completion: {labels}.",
        "mr": "वेळेत पूर्ण होऊ शकले नाही: {labels}.",
        "hi": "समय पर पूरा नहीं हो सका: {labels}।",
    },
    "pipeline_memory": {
        "en": "Real-time in-memory tracking pipeline.",
        "mr": "रिअल-टाइम इन-मेमरी ट्रॅकिंग पाइपलाइन.",
        "hi": "रीयल-टाइम इन-मेमोरी ट्रैकिंग पाइपलाइन।",
    },
    "partial": {
        "en": "Partial coverage; some district connections may be missing.",
        "mr": "अंशतः व्याप्ती; काही जिल्ह्यांचे दुवे उपलब्ध नसतील.",
        "hi": "आंशिक कवरेज; कुछ जिलों के कनेक्शन उपलब्ध नहीं हो सकते हैं।",
    },
}


def get_notice(key: str, lang: str = "en", **kwargs) -> str:
    """Retrieve formatted notice string with safe fallback to English."""
    lang_key = lang if lang in ("mr", "hi", "en") else "en"
    template_dict = NOTICES.get(key)
    if not template_dict:
        return ""
    template = template_dict.get(lang_key, template_dict.get("en", ""))
    if not template:
        return ""
    try:
        return template.format(**kwargs)
    except Exception:
        import re
        return re.sub(r"\{[a-zA-Z0-9_]+\}", "", template).strip()
