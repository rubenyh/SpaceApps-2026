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
# Intensifier between "duele" and the body part ("me duele mucho el estómago").
_INT = r"(mucho |muchisimo |bastante |un poco |algo )?"
_P = [
    ("shortness_of_breath", r"\b(me |le |te )?falt(a|aba|o) (mucho |muchisimo |bastante |un poco )?(el |de )?aire|\b(me|le) cuesta (un poco |mucho |bastante )?respirar|dificultad (para|al) respirar|respir\w+ con dificultad|disnea|sin aliento|no me entra (el )?aire|me quedo sin aire", {}),
    ("shortness_of_breath", r"\bno (puedo|puede|podia) respirar|\b(me|se) ahog\w*", {"severity": "severe"}),
    ("abnormal_breathing", r"\bno respira|respira (raro|mal|entrecortad\w*|de forma anormal)|respiracion (anormal|irregular|agonica)|\bjadea", {}),
    ("chest_pain", rf"dolor (de|en el) pecho|dolor toracico|(me|le) duele {_INT}el pecho|molestia en el pecho", {}),
    ("chest_pain", r"presion en el pecho|opresion (en el pecho|toracica)|pecho apretado|(me|le) aprieta el pecho", {"context": "pressure"}),
    ("cold_sweat", r"sudor frio|sudando frio|sudoracion fria", {}),
    ("palpitations", r"palpitacion\w*|el corazon (me |le )?(late|va) (muy )?(rapido|fuerte|acelerado|irregular)|corazon acelerado|taquicardi\w*|se (me|le) acelera el corazon|latidos (rapidos|irregulares|fuertes)", {}),
    ("speech_change", r"\bno (puedo|puede|podia|pude|pudo) hablar|(me|le) cuesta hablar|habla (rara|raro|arrastrad\w*|trabad\w*|confus\w*)|hablo (raro|arrastrado|trabado)|se (me|le) trab\w* (la lengua|el habla)|arrastr\w+ las palabras|dificultad para hablar|alteracion del habla|no (me|le) salen las palabras|lengua trabada", {}),
    ("facial_droop", r"(cara|boca|rostro) (caida|torcida|desviada|chueca)|se (me|le) cae (la cara|un lado de la cara|la boca)|asimetria facial|paralisis facial", {}),
    ("one_sided_weakness", r"debilidad (\w+ )?(en|de) (un|el|la|medio) (brazo|pierna|lado|mano|cuerpo)|debil de un lado|no (puedo|puede|podia) mover (el|la|un|una) (brazo|pierna|mano)|(brazo|pierna|mano) (dormid[oa]|sin fuerza|entumid[oa])|perd\w+ fuerza en (el|la|un|una)|se (me|le) durmio (el|la|un|una|medio|media) (brazo|pierna|mano|cara|lado|cuerpo)", {}),
    ("vision_loss", r"perd\w+ (la )?(vista|vision)|perdida (subita )?de (la )?vision|dej\w+ de ver|no (veo|ve) (de|por|con) un ojo|me quede ciego", {}),
    ("sudden_severe_headache", r"peor dolor de cabeza de (mi|su) vida|cefalea en trueno", {"onset": "sudden", "severity": "severe"}),
    ("headache", rf"dolor de cabeza|(me|le) duele {_INT}la cabeza|cefalea|migran\w*|jaqueca", {}),
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
    ("nausea", r"nausea\w*|ganas de vomitar|revuelto el estomago|estomago revuelto", {}),
    ("vomiting", r"(?<!ganas de )vomit\w*|devolv\w+", {}),
    ("repeated_vomiting", r"vomit\w* (\w+ )?(varias|muchas|repetidas|tres|cuatro|cinco) veces|\bno (puedo|puede) (dejar|parar) de vomitar|vomitos repetidos|sin parar de vomitar|vomitando sin parar|sigo vomitando|llevo todo el dia vomitando", {"persistence": "recurrent"}),
    ("diarrhea", r"diarrea|evacuaciones liquidas|heces liquidas", {}),
    ("low_fluid_intake", r"\bno he (bebido|tomado) (agua|liquidos)|(bebo|he bebido|tomo|he tomado) poc[ao] (agua|liquido)|\bcasi no (he )?(bebido|tomado agua)", {}),
    ("unable_to_keep_fluids", r"\bno (puedo|logro|consigo) (retener|tolerar|mantener) (liquidos|agua|nada)|vomito todo lo que (bebo|tomo)|\bno tolero (liquidos|agua|nada)|\bno retengo", {}),
    ("unable_to_keep_fluids", r"(tolero|retengo) (bien )?(los )?liquidos", {"status": "absent"}),
    ("low_urine_output", r"orino (muy )?poco|\bcasi no (he )?orina\w*|\bno he orinado|orina escasa|poca orina", {}),
    ("vomiting_blood", r"vomit\w* (con )?sangre|sangre en el vomito|hematemesis|posos de cafe", {}),
    ("abdominal_pain", rf"dolor (de|en el|en la) (estomago|abdomen|barriga|panza|vientre)|dolor abdominal|(me|le) duele {_INT}(el|la) (estomago|abdomen|barriga|panza|vientre)", {}),
    ("black_stool", r"heces (negras|alquitranadas)|evacuaciones negras|melena", {}),
    ("blood_in_stool", r"sangre en (las )?heces|heces con sangre|sangrado rectal", {}),
    ("heat_exposure", r"\bcalor\b|sobrecalent\w*|acalorad[oa]", {}),
    ("heavy_sweating", r"sudo mucho|sudando mucho|sudor (abundante|excesivo)|empapad[oa] (de|en) sudor|sudoracion (abundante|intensa)", {}),
    ("collapse", r"colaps\w*|desplom\w*", {}),
    ("urinary_burning", r"(ardor|dolor|escozor) al orinar|(me )?arde (al orinar|cuando orino)|duele al orinar|disuria", {}),
    ("urinary_urgency", r"urgencia (para|de|al) orinar|ganas (constantes|frecuentes) de orinar|orino (muy )?(seguido|a menudo)|necesidad urgente de orinar", {}),
    ("flank_pain", rf"dolor (de|en el) (costado|rinon|flanco)|(me|le) duele {_INT}(el|un) (costado|rinon|flanco)|dolor lumbar|dolor en la espalda baja", {}),
    ("visible_blood_in_urine", r"sangre en (la )?orina|orina con sangre|orina (roja|rosada)|hematuria|orino sangre", {}),
    ("unable_to_urinate", r"\bno (puedo|puede|logro|consigo|podia) orinar|incapaz de orinar|\bno (me|le) sale la orina", {}),
    ("muscle_pain", rf"dolor muscular|(me|le) duelen {_INT}los musculos|dolor (en|de) los musculos|mialgia|musculos adolorid\w*", {}),
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
# English phrases: the console UI is English, so a typed English report must reach the
# same rules (and the alarms) without Ollama. ponytail: common phrasings only, like the
# Spanish list; negation, onset and severity words below accept both languages.
_CANT = r"(can'?t|can ?not|unable to|could ?n'?t)"
_P += [
    ("shortness_of_breath", r"short(ness)? of breath|out of breath|breathless\w*|hard to breathe|(trouble|difficulty|problems?) breathing|struggling to breathe|can'?t catch my breath", {}),
    # "breath" for "breathe": a common typo and voice-transcription result.
    ("shortness_of_breath", rf"\b{_CANT} breathe?\b|\bchoking\b|suffocat\w*", {"severity": "severe"}),
    ("abnormal_breathing", r"\bnot breathing|\bgasping|breathing (strangely|abnormally|irregularly|weird\w*)", {}),
    ("chest_pain", r"chest (pain|discomfort|ache|hurts)|pain in (my|the|his|her|their) chest|(my|his|her) chest hurts", {}),
    ("chest_pain", r"chest (pressure|tightness)|pressure (in|on) (my|the) chest|tight(ness in the)? chest", {"context": "pressure"}),
    ("cold_sweat", r"cold sweat", {}),
    ("palpitations", r"\bpalpitations?\b|heart (is )?(racing|pounding|fluttering|skipping)|racing heart|irregular heart ?beat", {}),
    ("speech_change", rf"slurred speech|slurring|{_CANT} (speak|talk)|trouble (speaking|talking)", {}),
    ("facial_droop", r"facial droop|face (is )?droop\w*|drooping (face|mouth)", {}),
    ("one_sided_weakness", rf"weak(ness)? (on|in) one side|one[- ]sided weakness|{_CANT} move my (arm|leg|hand)|(arm|leg) (went|is) (numb|weak)", {}),
    ("vision_loss", rf"lost (my )?(vision|sight)|vision loss|{_CANT} see\b", {}),
    ("sudden_severe_headache", r"worst headache of my life|thunderclap headache", {"onset": "sudden", "severity": "severe"}),
    ("headache", r"head ?ache|my head hurts", {}),
    ("unresponsive", r"\bunresponsive|not responding|won'?t wake up|\bunconscious", {}),
    ("fainting", r"\bfaint(ed|ing)?\b|passed out|blacked out|lost consciousness", {}),
    ("seizure", r"\bseizure|\bfitting\b", {}),
    ("throat_swelling", r"throat (is )?(swelling|closing|swollen)|swollen (tongue|lips|throat)|tongue (is )?swell\w*", {}),
    ("hives", r"\bhives\b|\brash\b", {}),
    ("allergen_exposure", r"\ballerg\w*", {}),
    ("fever", r"\bfever\w*", {}),
    ("chills", r"\bchills\b|\bshivering", {}),
    ("cough", r"\bcough\w*", {}),
    ("malaise", r"feel(ing)? (sick|ill|unwell)|\bmalaise", {}),
    ("confusion", r"\bconfused\b|disoriented", {}),
    ("stiff_neck", r"stiff neck|neck (is )?stiff", {}),
    ("dizziness", r"\bdizz\w*|light-?headed\w*|room (is )?spinning", {}),
    ("nausea", r"\bnause\w*|feel like (throwing up|vomiting)", {}),
    ("vomiting", r"throwing up|threw up|(?<!feel like )\bvomiting", {}),
    ("diarrhea", r"diarrh\w*", {}),
    ("abdominal_pain", r"(stomach|abdominal|belly|tummy) (pain|ache|hurts)|stomach ?ache|my (stomach|belly|abdomen) hurts", {}),
    ("heat_exposure", r"\bheat\b|overheat\w*|too hot", {}),
    ("heavy_sweating", r"sweating (a lot|heavily|profusely)|heavy sweating|drenched in sweat", {}),
    ("collapse", r"\bcollaps\w*", {}),
    ("urinary_burning", r"burn(s|ing)? when (i )?(pee|urinat\w*)|pain(ful)? (when )?urinat\w*", {}),
    ("unable_to_urinate", rf"{_CANT} (pee|urinate)", {}),
    ("muscle_pain", r"muscle (pain|aches?)|sore muscles|muscles (hurt|ache)", {}),
    ("muscle_cramps", r"\bcramp\w*", {}),
    ("muscle_weakness", r"muscle weakness|weak muscles", {}),
    ("injury", r"\binjur\w*|\bi hit my|\bcut myself|\bsprain\w*", {}),
    ("head_injury", r"hit (my|his|her) head|head injury|bumped (my|his|her) head", {}),
    ("bleeding", r"\bbleed(ing|s)?\b", {}),
    ("heavy_bleeding", r"bleeding (heavily|a lot|badly)|heavy bleeding|won'?t stop bleeding|bleeding (that )?won'?t stop", {"severity": "severe"}),
    ("burn", r"\bburn(ed|t|s)?\b(?! when)", {}),
    ("severe_burn", r"(severe|bad|large|deep) burn", {"severity": "severe"}),
    ("cabin_alarm_reported", r"(co2|smoke|pressure|cabin|fire) alarm|smell(s)? (of )?smoke|pressure loss|air leak", {}),
    ("radiation_alert_reported", r"radiation (alarm|alert)|dosimeter (alarm|alert|is beeping)|solar (storm|particle event)", {}),
    # Only counts with a health complaint in the same message (see interpret()).
    ("multiple_crew_symptoms", r"\b(several|all|both|two|three|most|many) of us\b|\bwe (all|both)\b|\beveryone (here |on board |onboard )?(has|is|feels)\b|\bthe (whole|entire) crew\b|\b(several|multiple|other) crew ?(members|mates)\b", {}),
]
_PATTERNS = [(code, re.compile(rx), extra) for code, rx, extra in _P]

_NEGATOR = re.compile(r"\b(no|sin|ni|nunca|tampoco|jamas|niego|nada de|not|without|never|don'?t|dont|didn'?t|doesn'?t|haven'?t|hasn'?t|isn'?t|wasn'?t|deny|denies)\b")
# "no" that does not negate the symptom that follows.
_NEUTRAL_NO = re.compile(
    r"\bno (se|sabe|sabemos) (que|por que|como|cuando|donde|cual)\b"
    r"|\bno (se me |se le |se )?(quita|pasa|para|cede|mejora)\b"
    r"|\bsin (embargo|duda)\b"
)
_UNKNOWN = re.compile(r"\bno (se|sabe|sabemos|estoy segur[oa]( de)?) si\b|\b(not sure|don'?t know|unsure) (if|whether)\b")

_EDUCATIONAL = re.compile(
    r"\b(que es|que son|que causa\w*|que provoca\w*|por que se produce\w*|para que sirve\w*|como funciona\w*"
    r"|como se mide|explicame|explica|cuales son (los|las) (sintomas|causas|signos|senales)"
    r"|en que consiste|informacion sobre|informacion general|hablame de"
    r"|what is|what are|what causes|explain|tell me about)\b"
)
_HYPOTHETICAL = re.compile(
    r"\b(que pasa si|que pasaria si|que hago si|que hacer si|que (debo|debe|deberia) hacer si|que hago en caso"
    r"|si alguien|si alguna vez|si alguno|si un tripulante|si tuviera|si tuviese|si llegara|en caso de"
    r"|supongamos|hipotetic\w*"
    r"|what if|what (should|do|would|can) (i|we|you) do if|if (someone|anyone|a crew ?member) (gets|has)"
    r"|in case of|suppose|hypothetical\w*)\b"
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

_SUDDEN = re.compile(r"\b(de repente|repentin\w*|subit\w*|de golpe|de pronto|sin aviso|sudden\w*|out of nowhere)\b")
_GRADUAL = re.compile(r"\b(poco a poco|de a poco|gradual\w*|progresiv\w*|lentamente|slowly)\b")
_SEVERE = re.compile(
    r"\b((?<!poco )intens\w*|much[oa]s?|muchisim\w*|grave|muy fuerte|insoportable|sever[oa]|terrible|horrible"
    r"|el peor|la peor|severe|very bad|unbearable|extreme\w*|worst|a lot|very much)\b"
)
_MODERATE = re.compile(r"\b((?<!poco )fuerte|moderad[oa]|bastante|moderate)\b")
_MILD = re.compile(r"\b(leve|un poco|poquito|liger[oa]|algo de|suave|es poco(?! a poco)|poco (intens\w*|fuerte|dolor\w*)"
                   r"|mild|slight\w*|a (little|bit))\b")
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
    r"|algo no (anda|va) bien|no estoy bien|me siento fatal"
    r"|i (don'?t|do not) feel (well|good|right)|not feeling (well|good|right)"
    r"|i feel (bad|weird|strange|off|awful|terrible|funny)|something (is|feels) (off|wrong))\b"
)
# A concrete complaint outside the closed vocabulary ("me duele el oído"). Not negated.
_COMPLAINT = re.compile(
    r"(?<!no )(?<!no me )(?<!no le )(?<!no te )\b((me |le |te )?(duele\w*|arde|pica)\b"
    r"|(dolor|ardor|picor|comezon|hinchazon|inflamacion|sangrado|herida|grano|bulto)\b"
    r"|(hinchad|inflamad)\w*|color (roj|osc|amar|verd|blanc|negr|marr|caf|ros)\w*).*"
)
# Words that say something is wrong without naming a symptom ("malestar físico").
VAGUE = re.compile(
    r"\b(malestar|molestia|me siento (mal|rar[oa]|fatal)|no me siento bien|sintomas?|fisic[oa]"
    r"|algo (raro|anda mal|no va bien)|incomod\w*|mal\b"
    r"|discomfort|feel(ing)? (bad|weird|strange|off|awful|terrible|funny)|don'?t feel (well|good|right)"
    r"|something (is|feels) (off|wrong)|physical|uncomfortable)"
)
# Explicit call for help. "SOS" in capitals (lowercase "sos" is also a Spanish verb form).
_SOS_UPPER = re.compile(r"\bSOS\b")
_SOS = re.compile(r"\b(mayday|auxilio|socorro)\b")
_HEALTH = re.compile(
    r"\b(medic\w*|salud|sintoma\w*|enferm\w*|dolor\w*|duele|duelen|malestar|doctor\w*|sangre|orina\w*"
    r"|muestra|pulso|oxigeno|lesion|herida|cuerpo|radiacion|dosimetro"
    r"|symptoms?|pain|hurts?|sick|medical|health|doctor|blood|breath\w*|injur\w*|body|unwell)\b"
)
_READINGS = [
    (re.compile(r"oximetr\w*"), ("spo2", "heart_rate")),
    (re.compile(r"saturacion|\bspo2\b|oxigenacion|oxigeno en (la )?sangre"), ("spo2",)),
    (re.compile(r"\bpulso\b|frecuencia cardiaca|\bfrecuencia\b|\blpm\b|\bbpm\b"), ("heart_rate",)),
    (re.compile(r"oximeter"), ("spo2", "heart_rate")),
    (re.compile(r"\bsaturation|oxygen level|blood oxygen"), ("spo2",)),
    (re.compile(r"\bpulse\b|heart rate"), ("heart_rate",)),
]
_TOPICS = [
    ("loss_of_consciousness_or_seizure", r"desmay|sincope|convuls|epileps|inconscien|perdida de (la )?conciencia|faint|passing out|seizure|epilep|unconscious|loss of consciousness"),
    ("cabin_environment_alert", r"\bco2\b|dioxido de carbono|monoxido|calidad del aire|presion de (la )?cabina|despresuriz|humo|eclss|carbon dioxide|carbon monoxide|air quality|cabin pressure|depressuri|smoke"),
    ("radiation_alert", r"radiacion|dosimetr|\bdosis\b|rayos cosmicos|particulas solares|tormenta solar|radionucl|radiation|dosimet|\bdose\b|cosmic ray|solar particle|solar storm"),
    ("breathing_difficulty", r"respir|oximetr|saturacion|\bspo2\b|disnea|falta de aire|breath|oximet|saturation|oxygen"),
    ("severe_allergic_reaction", r"anafilax|alergi|alergic|urticaria|epinefrina|adrenalina|anaphyla|allerg|hives|epinephrine|adrenaline"),
    ("neurologic_red_flags", r"ictus|derrame cerebral|embolia|accidente cerebrovascular|\bacv\b|\bait\b|dolor de cabeza|cefalea|migran|stroke|\btia\b|headache|migraine"),
    ("chest_pain", r"infarto|dolor (de|en el) pecho|toracic|angina|coronari|heart attack|chest pain|angina|coronary"),
    ("heat_illness", r"golpe de calor|insolacion|\bcalor\b|hipertermi|heat stroke|heat exhaustion|\bheat\b|hypertherm|overheat"),
    ("injury_bleeding_or_burn", r"herida|quemadura|golpe|conmocion|contusion|sangrado|hemorragia|fractura|torcedura|wound|\bburns?\b|concussion|bruise|bleeding|hemorrhage|fracture|sprain|injur"),
    ("abdominal_pain_or_gi_bleeding", r"abdom|estomag|barriga|vientre|apendic|heces negras|gastritis|abdominal|stomach|belly|appendic|black stool|gastritis"),
    ("urinary_symptoms", r"orina|urinari|rinon|renal|calculo|vejiga|cistitis|pielonefritis|urine|urinary|kidney|bladder|cystitis"),
    ("muscle_symptoms", r"muscul|calambre|rabdomiolisis|muscle|cramp|rhabdo"),
    ("fever_or_respiratory_illness", r"fiebre|\btos\b|gripe|resfriad|catarro|virus|infeccion respiratoria|fever|cough|\bflu\b|\bcold\b|respiratory infection"),
    ("vomiting_diarrhea_or_dehydration", r"deshidrat|vomit|diarrea|nausea|hidrata|dehydrat|vomit|diarrh|nause|hydrat"),
    ("palpitations", r"arritmi|palpitac|\bpulso\b|frecuencia cardiaca|ritmo cardiaco|taquicardi|corazon|arrhythm|palpitation|heart rate|heart rhythm|tachycard|\bheart\b"),
    ("dizziness_or_space_motion_sickness", r"\bmareo|vertigo|cinetosis|adaptacion espacial|sindrome de adaptacion|dizz|vertigo|motion sickness|space adaptation"),
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


# --- Bounded spelling correction (typed typos and voice-transcription errors) ---
# Symptom words the rules above match, with the code each one leads to. A message word
# that is not one of them but sounds and reads like exactly one is replaced by it, and
# the rules run again on the corrected text: negation, timing and severity still come
# from the person's own words. Phrase words ("chest", "breathing") only change a result
# when the corrected text forms a whole rule phrase.
_SYMPTOM_WORDS = {
    "shortness_of_breath": "breathe breathing breathless shortness respirar",
    "chest_pain": "chest",
    "palpitations": "palpitations palpitaciones taquicardia",
    "speech_change": "slurred slurring",
    "headache": "headache headaches cefalea jaqueca migrana",
    "unresponsive": "unconscious unresponsive inconsciente",
    "fainting": "fainted fainting desmayo desmayado desmayada",
    "seizure": "seizure seizures convulsion convulsiones convulsionando",
    "hives": "urticaria ronchas",
    "fever": "fever feverish fiebre",
    "chills": "chills shivering escalofrios",
    "cough": "cough coughing tosiendo",
    "confusion": "confused disoriented confundido confundida desorientado desorientada",
    "dizziness": "dizzy dizziness lightheaded mareo mareos mareado mareada vertigo",
    "nausea": "nausea nauseous nauseated nauseas",
    "vomiting": "vomit vomiting vomito vomitando",
    "diarrhea": "diarrhea diarrhoea diarrea",
    "abdominal_pain": "stomach stomachache",
    "muscle_cramps": "cramps cramping calambres",
    "bleeding": "bleeding sangrando hemorragia",
    "burn": "quemadura",
}
_WORD_CODE = {w: code for code, words in _SYMPTOM_WORDS.items() for w in words.split()}
_REPORT_FRAME = re.compile(
    r"\b(i (have|had|am|feel|felt|got)|i'?m|i'?ve|having|feeling|(he|she|they) (has|have|is|are)"
    r"|tengo|siento|estoy|me (da|dio)|tiene)\b"
)
_PHRASE_WORDS = frozenset("breathe breathing shortness respirar chest slurred stomach".split())
# Real words one edit away from a symptom word. ponytail: hand-written list, not a
# dictionary; add a lookalike here when a test shows it being read as a symptom.
_LOOKALIKES = frozenset(
    "bleeping blending blessing breeding breather breathes chilly confuse confuses cramming fainter"
    " conversion crampons crashing dismiss distress failing fasting forever marcado marcada sleeping visiting"
    " stomachs vomits".split()
)
_SOUNDS = [(re.compile(rx), to) for rx, to in
           (("ph", "f"), ("ch", "k"), ("c", "k"), ("q", "k"), ("z", "s"), ("y", "i"), (r"(.)\1+", r"\1"))]


def _sound(word: str) -> str:
    for rx, to in _SOUNDS:
        word = rx.sub(to, word)
    return word


def _distance(a: str, b: str, limit: int = 1) -> int:
    """Edit distance with adjacent swaps (optimal string alignment), capped at limit + 1."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2, prev = None, list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            d = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            if prev2 is not None and i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                d = min(d, prev2[j - 2] + 1)
            cur.append(d)
        prev2, prev = prev, cur
    return min(prev[-1], limit + 1)


_SOUND_WORDS = [(_sound(w), w) for w in _WORD_CODE]


def _candidates(token: str) -> tuple[int, list[str]]:
    """(edits, closest symptom words) for a token that may be a misspelling. Bounded:
    6+ letters, same first letter, at most two edits after sound folding (z/s, y/i,
    c/k, doubled letters). One edit to one symptom is confident; anything else asks."""
    if len(token) < 6 or token in _WORD_CODE or token in _LOOKALIKES:
        return 3, []
    key = _sound(token)
    hits = [(_distance(key, s, 2), w) for s, w in _SOUND_WORDS if w[0] == token[0]]
    best = min((d for d, _ in hits), default=3)
    if best == 2 and len(token) < 7:
        return 3, []  # two edits in a short word reach too many real words
    return best, [w for d, w in hits if d == best <= 2]


def correct_spelling(text: str) -> tuple[str, tuple[tuple[str, str], ...], tuple[str, ...]]:
    """Normalized text -> (corrected text, corrections, codes of an unclear word)."""
    corrections: list[tuple[str, str]] = []
    ambiguous: list[str] = []

    def fix(m: re.Match) -> str:
        edits, words = _candidates(m.group(0))
        codes = list(dict.fromkeys(_WORD_CODE[w] for w in words))
        if edits <= 1 and len(codes) == 1:
            corrections.append((m.group(0), words[0]))
            return words[0]
        # Only words that name a symptom alone are worth a question ("chest" is not).
        unclear = {_WORD_CODE[w] for w in words if w not in _PHRASE_WORDS}
        ambiguous.extend(c for c in codes if c in unclear and c not in ambiguous)
        return m.group(0)

    return re.sub(r"[a-z]+", fix, text), tuple(corrections), tuple(ambiguous)


def is_sos(message: str) -> bool:
    text = normalize(message)
    return bool(
        _SOS_UPPER.search(message)
        or re.sub(r"\W", "", text) == "sos"
        or (_SOS.search(text) and not _HYPOTHETICAL.search(text))
    )


def interpret(request: AssistantRequest) -> Interpretation:
    text = normalize(request.message)
    other_message = bool(
        (request.reported_by and request.reported_by != request.astronaut_id)
        or _NAMED_OTHER.search(request.message)
    )
    observations = _text_observations(request.message, other_message)
    # Exact rules first; the corrected text only counts when it finds another symptom.
    fixed, corrections, ambiguous = correct_spelling(text)
    if corrections:
        retry = _text_observations(fixed, other_message)
        if {o.symptom for o in retry} - {o.symptom for o in observations}:
            observations = retry
            corrections = tuple(c for c in corrections if any(c[1] in o.evidence for o in retry))
            text = fixed
        else:
            corrections = ()

    # "Several of us are going to dinner" is no alarm: several crew members only count
    # with a symptom or a health complaint in the same message.
    complaint = any(o.status == "present" and o.symptom != "multiple_crew_symptoms" for o in observations)
    if not (complaint or _HEALTH.search(text) or VAGUE.search(text) or _UNWELL.search(text)):
        observations = [o for o in observations if o.symptom != "multiple_crew_symptoms"]

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
    # An unclear word only asks inside a report ("I have been coffing"), so "I keep
    # failing the test" does not turn into "Do you mean fainting?".
    options = () if final or not _REPORT_FRAME.search(text) else ambiguous
    if options and kind == "report":
        kind = "unclear"  # "dizzy or diarrhea?": ask which one
    medical = bool(final or options or topic or readings or kind == "unclear" or _HEALTH.search(text))
    complaint = None if reported_now or kind != "report" else _COMPLAINT.search(text)
    return Interpretation(
        observations=final,
        request_kind=kind,
        medical_signal=medical,
        mentions_readings=tuple(readings),
        topic_hint=topic,
        uncovered=complaint.group(0).strip()[:120] if complaint else None,
        corrections=corrections,
        spelling_options=options,
    )
