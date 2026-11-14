"""Spanish report -> Interpretation. Pure, deterministic, no I/O.

Text is lowercased and accent-stripped. Scopes:
- sentence (split on . ; ! ? and newlines): onset/severity fallback; a symptom-free sentence
  ("Ya se me pasó.") refers back to the previous one.
- segment (sentence split before pero/aunque/ahora/hoy): historical, resolved, "still happening".
- comma part: a hypothetical/educational marker governs its own clause and the later clauses
  of the same comma-delimited part ("No sé qué es, me duele el pecho" stays current).
- clause (segment split on commas, "y", and before "ni"): negation, "no sé si".
ponytail: phrase patterns cover the demo scenarios, not all Spanish; Ollama-assisted
extraction can be added later and validated against these observations.
"""

import re
import unicodedata
from dataclasses import replace as _replace

from onboard_api.assistant.workflows.medical.state import Interpretation, Observation
from onboard_api.schemas.assistant import AssistantRequest


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


# (code, pattern, defaults). Patterns are written lowercase without accents.
_P = [
    ("shortness_of_breath", r"\b(me |le |te )?falt(a|aba|o) (mucho |muchisimo |bastante |un poco )?(el |de )?aire|\b(me|le) cuesta respirar|dificultad (para|al) respirar|respir\w+ con dificultad|disnea|sin aliento|no me entra (el )?aire|me quedo sin aire", {}),
    ("shortness_of_breath", r"\bno (puedo|puede|podia) respirar|\b(me|se) ahog\w*", {"severity": "severe"}),
    ("abnormal_breathing", r"\bno respira|respira (raro|mal|entrecortad\w*|de forma anormal)|respiracion (anormal|irregular|agonica)|\bjadea", {}),
    ("chest_pain", r"dolor (de|en el) pecho|dolor toracico|(me|le) duele (el|mucho el) pecho|molestia en el pecho", {}),
    ("chest_pain", r"presion en el pecho|opresion (en el pecho|toracica)|pecho apretado|(me|le) aprieta el pecho", {"context": "pressure"}),
    ("cold_sweat", r"sudor frio|sudando frio|sudoracion fria", {}),
    ("palpitations", r"palpitacion\w*|el corazon (me |le )?(late|va) (muy )?(rapido|fuerte|acelerado|irregular)|corazon acelerado|taquicardi\w*|se (me|le) acelera el corazon|latidos (rapidos|irregulares|fuertes)", {}),
    ("speech_change", r"\bno (puedo|puede|podia|pude|pudo) hablar|(me|le) cuesta hablar|habla (rara|raro|arrastrad\w*|trabad\w*|confus\w*)|hablo (raro|arrastrado|trabado)|se (me|le) trab\w* (la lengua|el habla)|arrastr\w+ las palabras|dificultad para hablar|alteracion del habla|no (me|le) salen las palabras|lengua trabada", {}),
    ("facial_droop", r"(cara|boca|rostro) (caida|torcida|desviada|chueca)|se (me|le) cae (la cara|un lado de la cara|la boca)|asimetria facial|paralisis facial", {}),
    ("one_sided_weakness", r"debilidad (\w+ )?(en|de) (un|el|la|medio) (brazo|pierna|lado|mano|cuerpo)|debil de un lado|no (puedo|puede|podia) mover (el|la|un|una) (brazo|pierna|mano)|(brazo|pierna|mano) (dormid[oa]|sin fuerza|entumid[oa])|perd\w+ fuerza en (el|la|un|una)|se (me|le) durmio (el|la|un|una|medio|media) (brazo|pierna|mano|cara|lado|cuerpo)", {}),
    ("vision_loss", r"perd\w+ (la )?(vista|vision)|perdida (subita )?de (la )?vision|dej\w+ de ver|no (veo|ve) (de|por|con) un ojo|me quede ciego", {}),
    ("sudden_severe_headache", r"peor dolor de cabeza de (mi|su) vida|cefalea en trueno", {"onset": "sudden", "severity": "severe"}),
    ("headache", r"dolor de cabeza|(me|le) duele (mucho )?la cabeza|cefalea|migran\w*|jaqueca", {}),
    ("unresponsive", r"\bno responde|\bno reacciona|inconsciente|\bno (se )?despierta", {}),
    ("fainting", r"desmay\w*|me desvaneci|sincope|perd\w+ (el conocimiento|la conciencia)", {}),
    ("seizure", r"convuls\w*|ataque epileptico|crisis epileptica", {}),
    ("throat_swelling", r"se (me|le) (esta )?(cierra|cerrando|hincha|hinchando|inflama|inflamando) (la garganta|la lengua)|garganta (cerrada|hinchada)|hinchazon (de|en) (la )?(garganta|lengua|labios)|lengua hinchada|labios hinchados", {}),
    ("hives", r"ronchas|urticaria|habones|sarpullido", {}),
    ("allergen_exposure", r"alergi\w*|alergic\w*", {}),
    ("fever", r"fiebre|febril|calentura|temperatura alta", {}),
    ("chills", r"escalofrio\w*|tiritando", {}),
    ("cough", r"\btos\b|tosiendo|\btoso\b|\btose\b", {}),
    ("malaise", r"malestar general|decaid[oa]|me siento enferm[oa]|cuerpo cortado", {}),
    ("confusion", r"confundid[oa]|confusion|desorientad[oa]|\bno sabe donde esta|\bno se donde estoy|delira", {}),
    ("stiff_neck", r"rigidez (de|en el) cuello|cuello rigido|nuca rigida", {}),
    ("dizziness", r"\bmare\w*|vertigo|da vueltas|aturdid[oa]", {}),
    ("nausea", r"nausea\w*|ganas de vomitar|revuelto el estomago", {}),
    ("vomiting", r"(?<!ganas de )vomit\w*|devolv\w+", {}),
    ("repeated_vomiting", r"vomit\w* (\w+ )?(varias|muchas|repetidas|tres|cuatro|cinco) veces|\bno (puedo|puede) (dejar|parar) de vomitar|vomitos repetidos|sin parar de vomitar|vomitando sin parar|sigo vomitando|llevo todo el dia vomitando", {"persistence": "recurrent"}),
    ("diarrhea", r"diarrea|evacuaciones liquidas|heces liquidas", {}),
    ("low_fluid_intake", r"\bno he (bebido|tomado) (agua|liquidos)|(bebo|he bebido|tomo|he tomado) poc[ao] (agua|liquido)|\bcasi no (he )?(bebido|tomado agua)", {}),
    ("unable_to_keep_fluids", r"\bno (puedo|logro|consigo) (retener|tolerar|mantener) (liquidos|agua|nada)|vomito todo lo que (bebo|tomo)|\bno tolero (liquidos|agua|nada)|\bno retengo", {}),
    ("unable_to_keep_fluids", r"(tolero|retengo) (bien )?(los )?liquidos", {"status": "absent"}),
    ("low_urine_output", r"orino (muy )?poco|\bcasi no (he )?orina\w*|\bno he orinado|orina escasa|poca orina", {}),
    ("vomiting_blood", r"vomit\w* (con )?sangre|sangre en el vomito|hematemesis|posos de cafe", {}),
    ("abdominal_pain", r"dolor (de|en el|en la) (estomago|abdomen|barriga|panza|vientre)|dolor abdominal|(me|le) duele (el|la) (estomago|abdomen|barriga|panza|vientre)", {}),
    ("black_stool", r"heces (negras|alquitranadas)|evacuaciones negras|melena", {}),
    ("blood_in_stool", r"sangre en (las )?heces|heces con sangre|sangrado rectal", {}),
    ("heat_exposure", r"\bcalor\b|sobrecalent\w*|acalorad[oa]", {}),
    ("heavy_sweating", r"sudo mucho|sudando mucho|sudor (abundante|excesivo)|empapad[oa] (de|en) sudor|sudoracion (abundante|intensa)", {}),
    ("collapse", r"colaps\w*|desplom\w*", {}),
    ("urinary_burning", r"(ardor|dolor|escozor) al orinar|(me )?arde (al orinar|cuando orino)|duele al orinar|disuria", {}),
    ("urinary_urgency", r"urgencia (para|de|al) orinar|ganas (constantes|frecuentes) de orinar|orino (muy )?(seguido|a menudo)|necesidad urgente de orinar", {}),
    ("flank_pain", r"dolor (de|en el) (costado|rinon|flanco)|(me|le) duele (el|un) (costado|rinon|flanco)|dolor lumbar|dolor en la espalda baja", {}),
    ("visible_blood_in_urine", r"sangre en (la )?orina|orina con sangre|orina (roja|rosada)|hematuria|orino sangre", {}),
    ("unable_to_urinate", r"\bno (puedo|puede|logro|consigo|podia) orinar|incapaz de orinar|\bno (me|le) sale la orina", {}),
    ("muscle_pain", r"dolor muscular|(me|le) duelen (mucho )?los musculos|dolor (en|de) los musculos|mialgia|musculos adolorid\w*", {}),
    ("muscle_cramps", r"calambre\w*|espasmos? muscular\w*", {}),
    ("muscle_weakness", r"debilidad muscular|musculos debiles|sin fuerza en (los musculos|las piernas|los brazos)|debilidad (general|en las piernas|en los brazos)", {}),
    ("dark_urine", r"orina (de )?(color )?(a )?(cola|te|cafe|marron|oscura|negra|muy oscura)\b|orina como (cola|te|refresco)", {}),
    ("intense_exertion", r"ejercicio|entrenamiento|entrenar|entrene|esfuerzo|\beva\b|actividad extravehicular|caminata espacial|cinta de correr", {}),
    ("injury", r"\bgolpe\b|me golpee|se golpeo|herida|lesion|me corte|se corto|cortadura|torcedura|me lastime|se lastimo|fractura", {}),
    ("head_injury", r"golpe (fuerte )?(en|de) la cabeza|(me golpee|se golpeo|me pegue|se pego) (en )?la cabeza|traumatismo craneal", {}),
    ("bleeding", r"\bsangr(a|an|ando|o|e)\b|\bsangrado(?! rectal)|herida que sangra", {}),
    ("heavy_bleeding", r"sangra (mucho|abundante\w*|sin parar)|sangrando (mucho|sin parar|abundantemente)|sangrado (abundante|que no para|intenso|profuso)|hemorragia|mucha sangre|\bno (para|deja) de sangrar", {"severity": "severe"}),
    ("burn", r"quemadura|me queme|se quemo", {}),
    ("severe_burn", r"quemadura (grave|grande|extensa|profunda|severa|de tercer grado)|gran quemadura", {"severity": "severe"}),
    ("multiple_crew_symptoms", r"varios tripulantes|toda la tripulacion|todos (tenemos|estamos|sentimos|nos)|ambos (tenemos|estamos)|los (dos|tres) (tenemos|estamos)|varios de nosotros|a todos nos", {}),
    ("cabin_alarm_reported", r"alarma (de |del )?(co2|dioxido|humo|presion|cabina|aire|incendio|fuego|despresurizacion)|alerta de (co2|humo|presion|cabina|aire)|huele a humo|hay humo|perdida de presion|despresuriz\w*|fuga de aire", {}),
    ("radiation_alert_reported", r"(alarma|alerta) de (radiacion|particulas|dosis)|dosimetro (marca|suena|alerta|pita|da (una )?alarma)|suena el dosimetro|tormenta solar|evento de particulas", {}),
]
_PATTERNS = [(code, re.compile(rx), extra) for code, rx, extra in _P]

_NEGATOR = re.compile(r"\b(no|sin|ni|nunca|tampoco|jamas|niego|nada de)\b")
# "no" that does not negate the symptom that follows.
_NEUTRAL_NO = re.compile(
    r"\bno (se|sabe|sabemos) (que|por que|como|cuando|donde|cual)\b"
    r"|\bno (se me |se le |se )?(quita|pasa|para|cede|mejora)\b"
    r"|\bsin (embargo|duda)\b"
)
_UNKNOWN = re.compile(r"\bno (se|sabe|sabemos|estoy segur[oa]( de)?) si\b")

_EDUCATIONAL = re.compile(
    r"\b(que es|que son|que causa\w*|que provoca\w*|por que se produce\w*|para que sirve\w*|como funciona\w*"
    r"|como se mide|explicame|explica|cuales son (los|las) (sintomas|causas|signos|senales)"
    r"|en que consiste|informacion sobre|hablame de)\b"
)
_HYPOTHETICAL = re.compile(
    r"\b(que pasa si|que pasaria si|que hago si|que hacer si|que (debo|debe|deberia) hacer si|que hago en caso"
    r"|si alguien|si alguna vez|si alguno|si un tripulante|si tuviera|si tuviese|si llegara|en caso de"
    r"|supongamos|hipotetic\w*)\b"
)
# "hace <duración>" is historical, except "hace <duración> que" + non-past verb, which is
# ongoing persistence ("Hace tiempo que me falta el aire"; "hace tiempo que tuve..." stays historical).
_AGO = (r"hace ((\d+|un|una|unos|unas|dos|tres|cuatro|cinco|seis|varios|varias|muchos|muchas)"
        r" (anos?|mes|meses|semanas?)|(mucho )?tiempo)")
_HISTORICAL = re.compile(
    rf"\b{_AGO}\b(?! que\b)|\b{_AGO} que (me |le |se )?(tuve|tuvo|sufri|sufrio|dio|paso|desmaye|desmayo)\b"
    r"|\b(el|este) (ano|mes) pasado\b|\bla (semana|mision) pasada\b|\bantes tenia\b|\bde nin[oa]\b"
    r"|\ben el pasado\b|\ben otra mision\b|\bantes de la mision\b|\bantecedente"
)
_RESOLVED = re.compile(
    r"\bya (se me|se le|se) (paso|quito|fue|resolvio)\b|\bya (paso|cedio|desaparecio|se recupero|desperto"
    r"|reacciona|responde|esta bien|estoy bien|me siento bien)\b|\bse (me|le) (paso|quito)\b"
    r"|\bduro (unos|un par de|pocos|algunos) (segundos|minutos)\b|\by (luego )?(paso|cedio|se fue|se quito)\b"
    r"|\bcedio\b|\bse resolvio\b|\brecupero (la conciencia|el conocimiento)\b"
)
_STILL = re.compile(r"\b(ahora|todavia|aun|sigo|sigue|persiste)\b")
_SEGMENT = re.compile(r"(?=\b(?:pero|aunque|ahora|hoy|actualmente)\b)")
_CLAUSE = re.compile(r",|\by\b|\be\b|(?=\bni\b)")
_SENTENCE = re.compile(r"[.;!?¿¡\n]+")

_OTHER = re.compile(
    r"\b(mi companer[oa]|el comandante|la comandante|otr[oa] tripulante|un tripulante|una tripulante"
    r"|el piloto|la piloto|mi colega|el ingeniero|la ingeniera|el especialista|la especialista)\b"
    r"|\b(le|se le) (duele|duelen|falta|cuesta|traba|cae|hincha|cierra|sale|dio)\b|\bno responde\b"
    r"|\besta inconsciente\b|\bse desmayo\b|\bconvulsiona\b|\besta confundid[oa]\b|\bno reacciona\b"
)
# "<Name> no responde": a capitalised name followed by a third-person verb (original text).
_NAMED_OTHER = re.compile(
    r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+ (no responde|no reacciona|se desmay|est[aá] inconsciente|convulsiona"
    r"|se golpe|se cort|se quem|est[aá] confundid)"
)

_SUDDEN = re.compile(r"\b(de repente|repentin\w*|subit\w*|de golpe|de pronto|sin aviso)\b")
_GRADUAL = re.compile(r"\b(poco a poco|de a poco|gradual\w*|progresiv\w*|lentamente)\b")
_SEVERE = re.compile(
    r"\b((?<!poco )intens\w*|much[oa]s?|muchisim\w*|grave|muy fuerte|insoportable|sever[oa]|terrible|horrible"
    r"|el peor|la peor)\b"
)
_MODERATE = re.compile(r"\b((?<!poco )fuerte|moderad[oa]|bastante)\b")
_MILD = re.compile(r"\b(leve|un poco|poquito|liger[oa]|algo de|suave|es poco(?! a poco)|poco (intens\w*|fuerte|dolor\w*))\b")
_ONGOING = re.compile(
    rf"\b{_AGO} que\b|"
    r"\b(sigue|sigo|todavia|aun|persiste|no se (me |le )?(quita|pasa)|desde (hace|ayer|anoche|esta manana|la manana|hoy)"
    r"|llevo|lleva|cada vez (peor|mas)|empeora\w*|constante|continu\w*|todo el dia)\b"
)
_RECURRENT = re.compile(
    r"\b(otra vez|de nuevo|vuelve|volvio|se repite|repetid\w*|varias veces|va y viene|van y vienen|en oleadas)\b"
)
_ADAPTATION = re.compile(
    r"\b(adaptacion|microgravedad|ingravidez|primer(os)? dias?|recien llegad\w*|desde (el lanzamiento|que llegamos|la llegada)"
    r"|al mover la cabeza|al girar la cabeza|al moverme)\b"
)
_UNWELL = re.compile(
    r"\b(no me siento bien|me siento mal|me encuentro mal|no me encuentro bien|me siento rar[oa]"
    r"|algo no (anda|va) bien|no estoy bien|me siento fatal)\b"
)
_HEALTH = re.compile(
    r"\b(medic\w*|salud|sintoma\w*|enferm\w*|dolor\w*|duele|duelen|malestar|doctor\w*|sangre|orina\w*"
    r"|muestra|pulso|oxigeno|lesion|herida|cuerpo|radiacion|dosimetro)\b"
)
_READINGS = [
    (re.compile(r"oximetr\w*"), ("spo2", "heart_rate")),
    (re.compile(r"saturacion|\bspo2\b|oxigenacion|oxigeno en (la )?sangre"), ("spo2",)),
    (re.compile(r"\bpulso\b|frecuencia cardiaca|\bfrecuencia\b|\blpm\b|\bbpm\b"), ("heart_rate",)),
]
_TOPICS = [
    ("loss_of_consciousness_or_seizure", r"desmay|sincope|convuls|epileps|inconscien|perdida de (la )?conciencia"),
    ("cabin_environment_alert", r"\bco2\b|dioxido de carbono|monoxido|calidad del aire|presion de (la )?cabina|despresuriz|humo|eclss"),
    ("radiation_alert", r"radiacion|dosimetr|\bdosis\b|rayos cosmicos|particulas solares|tormenta solar|radionucl"),
    ("breathing_difficulty", r"respir|oximetr|saturacion|\bspo2\b|disnea|falta de aire"),
    ("severe_allergic_reaction", r"anafilax|alergi|alergic|urticaria|epinefrina|adrenalina"),
    ("neurologic_red_flags", r"ictus|derrame cerebral|embolia|accidente cerebrovascular|\bacv\b|\bait\b|dolor de cabeza|cefalea|migran"),
    ("chest_pain", r"infarto|dolor (de|en el) pecho|toracic|angina|coronari"),
    ("heat_illness", r"golpe de calor|insolacion|\bcalor\b|hipertermi"),
    ("injury_bleeding_or_burn", r"herida|quemadura|golpe|conmocion|contusion|sangrado|hemorragia|fractura|torcedura"),
    ("abdominal_pain_or_gi_bleeding", r"abdom|estomag|barriga|vientre|apendic|heces negras|gastritis"),
    ("urinary_symptoms", r"orina|urinari|rinon|renal|calculo|vejiga|cistitis|pielonefritis"),
    ("muscle_symptoms", r"muscul|calambre|rabdomiolisis"),
    ("fever_or_respiratory_illness", r"fiebre|\btos\b|gripe|resfriad|catarro|virus|infeccion respiratoria"),
    ("vomiting_diarrhea_or_dehydration", r"deshidrat|vomit|diarrea|nausea|hidrata"),
    ("palpitations", r"arritmi|palpitac|\bpulso\b|frecuencia cardiaca|ritmo cardiaco|taquicardi|corazon"),
    ("dizziness_or_space_motion_sickness", r"\bmareo|vertigo|cinetosis|adaptacion espacial|sindrome de adaptacion"),
]
_TOPICS_RX = [(re.compile(rx), card) for card, rx in _TOPICS]

# Card used for retrieval when the text names a symptom but no topic keyword.
CODE_CARD = {
    "shortness_of_breath": "breathing_difficulty", "abnormal_breathing": "breathing_difficulty",
    "chest_pain": "chest_pain", "cold_sweat": "chest_pain", "palpitations": "palpitations",
    "speech_change": "neurologic_red_flags", "facial_droop": "neurologic_red_flags",
    "one_sided_weakness": "neurologic_red_flags", "vision_loss": "neurologic_red_flags",
    "sudden_severe_headache": "neurologic_red_flags", "headache": "neurologic_red_flags",
    "unresponsive": "loss_of_consciousness_or_seizure", "fainting": "loss_of_consciousness_or_seizure",
    "seizure": "loss_of_consciousness_or_seizure", "throat_swelling": "severe_allergic_reaction",
    "hives": "severe_allergic_reaction", "allergen_exposure": "severe_allergic_reaction",
    "fever": "fever_or_respiratory_illness", "chills": "fever_or_respiratory_illness",
    "cough": "fever_or_respiratory_illness", "malaise": "fever_or_respiratory_illness",
    "stiff_neck": "fever_or_respiratory_illness", "dizziness": "dizziness_or_space_motion_sickness",
    "nausea": "vomiting_diarrhea_or_dehydration", "vomiting": "vomiting_diarrhea_or_dehydration",
    "diarrhea": "vomiting_diarrhea_or_dehydration", "low_fluid_intake": "vomiting_diarrhea_or_dehydration",
    "unable_to_keep_fluids": "vomiting_diarrhea_or_dehydration",
    "low_urine_output": "vomiting_diarrhea_or_dehydration",
    "repeated_vomiting": "vomiting_diarrhea_or_dehydration",
    "vomiting_blood": "abdominal_pain_or_gi_bleeding", "abdominal_pain": "abdominal_pain_or_gi_bleeding",
    "black_stool": "abdominal_pain_or_gi_bleeding", "blood_in_stool": "abdominal_pain_or_gi_bleeding",
    "heat_exposure": "heat_illness", "heavy_sweating": "heat_illness", "collapse": "heat_illness",
    "urinary_burning": "urinary_symptoms", "urinary_urgency": "urinary_symptoms",
    "flank_pain": "urinary_symptoms", "visible_blood_in_urine": "urinary_symptoms",
    "unable_to_urinate": "urinary_symptoms", "muscle_pain": "muscle_symptoms",
    "muscle_cramps": "muscle_symptoms", "muscle_weakness": "muscle_symptoms",
    "dark_urine": "muscle_symptoms", "intense_exertion": "muscle_symptoms",
    "injury": "injury_bleeding_or_burn", "head_injury": "injury_bleeding_or_burn",
    "bleeding": "injury_bleeding_or_burn", "heavy_bleeding": "injury_bleeding_or_burn",
    "burn": "injury_bleeding_or_burn", "severe_burn": "injury_bleeding_or_burn",
    "multiple_crew_symptoms": "cabin_environment_alert", "cabin_alarm_reported": "cabin_environment_alert",
    "radiation_alert_reported": "radiation_alert", "confusion": "neurologic_red_flags",
}


def cabin_alarm_type(text: str) -> str:
    if re.search(r"co2|dioxido", text):
        return "co2"
    if re.search(r"humo|incendio|fuego", text):
        return "smoke"
    if re.search(r"presion|despresuriz|fuga", text):
        return "pressure"
    return "other"


def _first(rx_value: list[tuple[re.Pattern, str]], *texts: str) -> str | None:
    for text in texts:
        for rx, value in rx_value:
            if rx.search(text):
                return value
    return None


def _onset(*texts: str):
    return _first([(_SUDDEN, "sudden"), (_GRADUAL, "gradual")], *texts)


def _severity(*texts: str):
    return _first([(_SEVERE, "severe"), (_MODERATE, "moderate"), (_MILD, "mild")], *texts)


def _persistence(*texts: str):
    return _first([(_RECURRENT, "recurrent"), (_ONGOING, "ongoing")], *texts)


def _rank(o: Observation) -> int:
    """Which duplicate observation of one code wins (lower first)."""
    if o.status == "present":
        return {"current": 0, "resolved": 1, "historical": 4, "hypothetical": 5}[o.temporality]
    return 2 if o.status == "unknown" else 3


def _text_observations(message: str, other_message: bool) -> list[Observation]:
    found: list[Observation] = []
    previous: list[int] = []  # indexes of the previous sentence's observations
    for sentence in _SENTENCE.split(normalize(message)):
        if not sentence.strip():
            continue
        start = len(found)
        seg_previous: list[int] = []
        for segment in _SEGMENT.split(sentence):
            historical = bool(_HISTORICAL.search(segment))
            resolved = bool(_RESOLVED.search(segment)) and not _STILL.search(segment)
            other = other_message or bool(_OTHER.search(segment) or _OTHER.search(sentence))
            seg_start = len(found)
            clauses = []
            for part in segment.split(","):
                governed = False
                for clause in _CLAUSE.split(part):
                    governed = governed or bool(_HYPOTHETICAL.search(clause) or _EDUCATIONAL.search(clause))
                    clauses.append((clause, governed))
            for clause, hypothetical in clauses:
                for code, rx, extra in _PATTERNS:
                    m = rx.search(clause)
                    if not m:
                        continue
                    prefix = _NEUTRAL_NO.sub(" ", clause[: m.start()])
                    if _UNKNOWN.search(prefix):
                        status = "unknown"
                    elif _NEGATOR.search(prefix) or clause.lstrip().startswith("ni "):
                        status = "absent"
                    else:
                        status = extra.get("status", "present")
                    if hypothetical:
                        temporality = "hypothetical"
                    elif historical:
                        temporality = "historical"
                    elif resolved:
                        temporality = "resolved"
                    else:
                        temporality = "current"
                    persistence = extra.get("persistence") or _persistence(clause, segment)
                    if temporality == "resolved":
                        persistence = "resolved"
                    context = None
                    if code == "cabin_alarm_reported":
                        context = cabin_alarm_type(sentence)
                    elif code in ("dizziness", "nausea", "vomiting") and _ADAPTATION.search(normalize(message)):
                        context = "adaptation"
                    found.append(Observation(
                        symptom=code,
                        status=status,
                        origin="text",
                        evidence=m.group(0).strip(),
                        temporality=temporality,
                        subject="other" if other else "self",
                        onset=extra.get("onset") or _onset(clause, sentence),
                        severity=extra.get("severity") or _severity(clause, sentence),
                        persistence=persistence,
                        context=extra.get("context") or context,
                    ))
            if len(found) == seg_start and resolved:
                # "Me desmayé, pero ya estoy bien": refers back to the previous segment.
                for i in seg_previous:
                    if found[i].status == "present" and found[i].temporality == "current":
                        found[i] = _replace(found[i], temporality="resolved", persistence="resolved")
            elif len(found) > seg_start:
                seg_previous = list(range(seg_start, len(found)))
        resolved = bool(_RESOLVED.search(sentence))
        if len(found) == start and previous:
            # "Ya se me pasó." / "Empezó poco a poco y es leve." alone refer back
            # to the previous sentence's present symptoms.
            onset, severity = _onset(sentence), _severity(sentence)
            for i in previous:
                o = found[i]
                if o.status != "present":
                    continue
                o = _replace(o, onset=o.onset or onset, severity=o.severity or severity)
                if resolved and o.temporality == "current":
                    o = _replace(o, temporality="resolved", persistence="resolved")
                found[i] = o
        elif len(found) > start:
            previous = list(range(start, len(found)))
    return found


def interpret(request: AssistantRequest) -> Interpretation:
    text = normalize(request.message)
    other_message = bool(
        (request.reported_by and request.reported_by != request.astronaut_id)
        or _NAMED_OTHER.search(request.message)
    )
    observations = _text_observations(request.message, other_message)

    # sudden + severe headache is the neurologic red flag.
    for o in list(observations):
        if o.symptom == "headache" and o.onset == "sudden" and o.severity == "severe":
            observations.append(_replace(o, symptom="sudden_severe_headache"))

    # Structured entries override text of the same code (status and onset/severity/persistence),
    # except for safety: text reporting the symptom present (current or resolved) is kept when the
    # structured entry says absent/unknown, and the dedupe below keeps the present one. Applied to
    # every code (a superset of the alarm-capable ones).
    structured = {s.symptom: s.status for s in request.reported_symptoms}
    observations = [
        o for o in observations
        if o.symptom not in structured
        or (structured[o.symptom] != "present" and o.status == "present"
            and o.temporality in ("current", "resolved"))
    ]
    for s in request.reported_symptoms:
        context = s.context
        if context and s.symptom in ("dizziness", "nausea", "vomiting") and _ADAPTATION.search(normalize(context)):
            context = "adaptation"
        observations.append(Observation(
            symptom=s.symptom,
            status=s.status,
            origin="structured",
            evidence="structured",
            temporality="resolved" if s.persistence == "resolved" else "current",
            subject="other" if other_message else "self",
            onset=s.onset,
            severity=s.severity,
            persistence=s.persistence,
            context=context,
        ))

    best: dict[str, Observation] = {}
    for o in observations:
        if o.symptom not in best or _rank(o) < _rank(best[o.symptom]):
            best[o.symptom] = o
    final = tuple(best.values())

    reported_now = any(o.status == "present" and o.temporality in ("current", "resolved") for o in final)
    if reported_now:
        kind = "report"
    elif _EDUCATIONAL.search(text) or _HYPOTHETICAL.search(text):
        kind = "educational"
    elif _UNWELL.search(text):
        kind = "unclear"
    else:
        kind = "report"

    readings = sorted({k for rx, kinds in _READINGS if rx.search(text) for k in kinds})
    topic = _first(_TOPICS_RX, text) or next(
        (CODE_CARD[o.symptom] for o in final if o.status == "present"), None
    )
    medical = bool(final or topic or readings or kind == "unclear" or _HEALTH.search(text))
    return Interpretation(
        observations=final,
        request_kind=kind,
        medical_signal=medical,
        mentions_readings=tuple(readings),
        topic_hint=topic,
    )

