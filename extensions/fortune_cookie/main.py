import json
import os
import random

LANGS = ("en", "es")

FORTUNES = [
    ("A closed mouth catches no flies.", "En boca cerrada no entran moscas."),
    ("A journey of a thousand miles begins with a single step.", "Un viaje de mil millas empieza con un solo paso."),
    ("All that glitters is not gold.", "No todo lo que brilla es oro."),
    ("An apple a day keeps the doctor away.", "Una manzana al día mantiene alejado al médico."),
    ("Beware of the man who has nothing to lose.", "Cuidado con quien no tiene nada que perder."),
    ("Don't count your chickens before they hatch.", "No vendas la piel del oso antes de cazarlo."),
    ("Every cloud has a silver lining.", "No hay mal que por bien no venga."),
    ("Fortune favors the bold.", "La fortuna favorece a los valientes."),
    ("Haste makes waste.", "Las prisas son malas consejeras."),
    ("If you want something done right, do it yourself.", "Si quieres algo bien hecho, hazlo tú mismo."),
    ("Knowledge is power.", "El saber es poder."),
    ("Laughter is the best medicine.", "La risa es la mejor medicina."),
    ("Measure twice, cut once.", "Mide dos veces, corta una."),
    ("Necessity is the mother of invention.", "La necesidad es la madre de la invención."),
    ("No gain without pain.", "Quien algo quiere, algo le cuesta."),
    ("Nothing ventured, nothing gained.", "Quien no arriesga, no gana."),
    ("Practice what you preach.", "Predica con el ejemplo."),
    ("Rome wasn't built in a day.", "Roma no se construyó en un día."),
    ("Still waters run deep.", "Del agua mansa líbrame Dios."),
    ("The early bird catches the worm.", "El que madruga, Dios lo ayuda."),
    ("The pen is mightier than the sword.", "Más poderosa es la pluma que la espada."),
    ("There's no place like home.", "No hay nada como el hogar."),
    ("Time flies when you're having fun.", "El tiempo vuela cuando te diviertes."),
    ("To err is human; to forgive divine.", "Errar es humano, perdonar es divino."),
    ("Well begun is half done.", "Obra empezada, medio acabada."),
    ("When in Rome, do as the Romans do.", "Donde fueres, haz lo que vieres."),
    ("You can't judge a book by its cover.", "El hábito no hace al monje."),
    ("You reap what you sow.", "Cosechas lo que siembras."),
    ("A rolling stone gathers no moss.", "Piedra que rueda no cría moho."),
    ("Actions speak louder than words.", "Los hechos hablan más alto que las palabras."),
    ("Beauty is in the eye of the beholder.", "La belleza está en los ojos de quien mira."),
    ("Cleanliness is next to godliness.", "La limpieza es lo más cercano a la santidad."),
    ("Curiosity killed the cat.", "La curiosidad mató al gato."),
    ("Discretion is the better part of valor.", "La prudencia es la mejor parte del valor."),
    ("East or west, home is best.", "Este u oeste, el hogar es lo mejor."),
    ("Every man has his price.", "Todo hombre tiene un precio."),
    ("Good things come to those who wait.", "Lo bueno llega a quien sabe esperar."),
    ("Honesty is the best policy.", "La honestidad es la mejor política."),
    ("If at first you don't succeed, try, try again.", "Si al principio no lo consigues, inténtalo otra vez."),
    ("Ignorance is bliss.", "La ignorancia es felicidad."),
    ("It takes two to tango.", "Para bailar tango hacen falta dos."),
    ("Let sleeping dogs lie.", "No despiertes al perro dormido."),
    ("Look before you leap.", "Mira antes de saltar."),
    ("Many hands make light work.", "Muchas manos aligeran el trabajo."),
    ("Out of sight, out of mind.", "Ojos que no ven, corazón que no siente."),
    ("Patience is a virtue.", "La paciencia es una virtud."),
    ("Pride comes before a fall.", "La soberbia precede a la caída."),
    ("Silence is golden.", "El silencio vale oro."),
    ("The grass is always greener on the other side.", "La hierba siempre es más verde en el jardín ajeno."),
    ("The more things change, the more they stay the same.", "Cuanto más cambian las cosas, más iguales se quedan."),
    ("There's no smoke without fire.", "Cuando el río suena, agua lleva."),
    ("Too many cooks spoil the broth.", "Demasiados cocineros arruinan el caldo."),
    ("Variety is the spice of life.", "En la variedad está el gusto."),
    ("What goes around comes around.", "Quien siembra vientos recoge tempestades."),
    ("You can lead a horse to water, but you can't make it drink.", "Puedes llevar el caballo al agua, pero no obligarlo a beber."),
    ("Your future is as bright as your faith.", "Tu futuro es tan brillante como tu fe."),
    ("A change is as good as a rest.", "Un cambio es tan bueno como un descanso."),
    ("Birds of a feather flock together.", "Cada oveja con su pareja."),
    ("Charity begins at home.", "La caridad empieza en casa."),
    ("Desperate times call for desperate measures.", "A grandes males, grandes remedios."),
    ("Don't bite the hand that feeds you.", "No muerdas la mano que te da de comer."),
    ("Don't put all your eggs in one basket.", "No pongas todos los huevos en la misma cesta."),
    ("Every dog has its day.", "Cada perro tiene su día."),
    ("Fools rush in where angels fear to tread.", "Los necios se precipitan donde los ángeles temen pisar."),
    ("Give a man a fish and you feed him for a day; teach a man to fish and you feed him for a lifetime.", "Dale a un hombre un pez y comerá un día; enséñalo a pescar y comerá toda la vida."),
    ("Half a loaf is better than none.", "Más vale algo que nada."),
    ("If the shoe fits, wear it.", "Al que le venga el guante, que se lo plante."),
    ("It's no use crying over spilled milk.", "De nada sirve llorar por la leche derramada."),
    ("Keep your friends close and your enemies closer.", "Mantén a tus amigos cerca y a tus enemigos más cerca."),
    ("Love is blind.", "El amor es ciego."),
    ("Money doesn't grow on trees.", "El dinero no crece en los árboles."),
    ("Old habits die hard.", "Genio y figura hasta la sepultura."),
    ("One man's trash is another man's treasure.", "La basura de uno es el tesoro de otro."),
    ("People who live in glass houses shouldn't throw stones.", "Quien vive en casa de cristal, no tira piedras."),
    ("Seeing is believing.", "Ver para creer."),
    ("The best things in life are free.", "Lo mejor de la vida es gratis."),
    ("The devil is in the details.", "El diablo está en los detalles."),
    ("The squeaky wheel gets the grease.", "La rueda que chirría es la que se engrasa."),
    ("There's more than one way to skin a cat.", "Hay más de un modo de pelar un gato."),
    ("Two heads are better than one.", "Cuatro ojos ven más que dos."),
    ("When it rains, it pours.", "Las desgracias nunca vienen solas."),
    ("You can't have your cake and eat it too.", "No se puede estar en misa y repicando."),
    ("A friend in need is a friend indeed.", "Amigo en la adversidad, amigo de verdad."),
    ("All good things must come to an end.", "Todo lo bueno tiene un final."),
    ("Better late than never.", "Más vale tarde que nunca."),
    ("Blood is thicker than water.", "La sangre tira."),
    ("Don't make a mountain out of a molehill.", "No hagas una montaña de un grano de arena."),
    ("Easy come, easy go.", "Lo que fácil viene, fácil se va."),
    ("Forewarned is forearmed.", "Hombre prevenido vale por dos."),
    ("Great minds think alike.", "Las grandes mentes piensan igual."),
    ("History repeats itself.", "La historia se repite."),
    ("If you can't beat 'em, join 'em.", "Si no puedes con ellos, únete a ellos."),
    ("It's better to be safe than sorry.", "Más vale prevenir que lamentar."),
    ("Let bygones be bygones.", "Lo pasado, pasado está."),
    ("Murphy's law: anything that can go wrong will go wrong.", "Ley de Murphy: si algo puede salir mal, saldrá mal."),
    ("Nobody is perfect.", "Nadie es perfecto."),
    ("Once bitten, twice shy.", "Gato escaldado del agua fría huye."),
    ("Practice makes perfect.", "La práctica hace al maestro."),
    ("The end justifies the means.", "El fin justifica los medios."),
    ("The truth shall set you free.", "La verdad os hará libres."),
    ("Waste not, want not.", "Quien guarda, halla."),
    ("You are the master of your own destiny.", "Eres el dueño de tu destino."),
    ("A picture is worth a thousand words.", "Una imagen vale más que mil palabras."),
    ("Absence makes the heart grow fonder.", "La ausencia hace crecer el cariño."),
    ("All work and no play makes Jack a dull boy.", "Mucho trabajo y poco juego hacen de Jack un chico aburrido."),
    ("Beggars can't be choosers.", "Los mendigos no pueden elegir."),
    ("Better to light a candle than to curse the darkness.", "Mejor encender una vela que maldecir la oscuridad."),
    ("Don't burn your bridges.", "No quemes tus naves."),
    ("Empty vessels make the most noise.", "El cántaro vacío es el que más suena."),
    ("Every rose has its thorn.", "Toda rosa tiene su espina."),
    ("Failing to plan is planning to fail.", "No planificar es planificar el fracaso."),
    ("Fortune favors the prepared mind.", "La fortuna favorece a la mente preparada."),
    ("Good fences make good neighbors.", "Las buenas cercas hacen buenos vecinos."),
    ("He who laughs last laughs best.", "Quien ríe el último, ríe mejor."),
    ("If you can't stand the heat, get out of the kitchen.", "Si no aguantas el calor, sal de la cocina."),
    ("It's always darkest before the dawn.", "Siempre está más oscuro antes del amanecer."),
    ("Keep it simple, stupid.", "Hazlo simple, estúpido."),
    ("Never put off till tomorrow what you can do today.", "No dejes para mañana lo que puedes hacer hoy."),
    ("One good turn deserves another.", "Un favor con otro se paga."),
    ("Out of the frying pan and into the fire.", "Salir de Guatemala para entrar en Guatepeor."),
    ("The best defense is a good offense.", "La mejor defensa es un buen ataque."),
    ("The customer is always right.", "El cliente siempre tiene la razón."),
    ("The road to hell is paved with good intentions.", "El camino al infierno está empedrado de buenas intenciones."),
    ("There is no such thing as a free lunch.", "No hay almuerzos gratis."),
    ("Two wrongs don't make a right.", "Dos males no hacen un bien."),
    ("When the going gets tough, the tough get going.", "Cuando la cosa se pone dura, los duros se ponen en marcha."),
    ("You can't make an omelette without breaking eggs.", "No se hace tortilla sin romper huevos."),
    ("Don't look a gift horse in the mouth.", "A caballo regalado no le mires el diente."),
    ("A bird in the hand is worth two in the bush.", "Más vale pájaro en mano que ciento volando."),
    ("A man is known by the company he keeps.", "Dime con quién andas y te diré quién eres."),
    ("This too shall pass.", "No hay mal que dure cien años."),
    ("What's done is done.", "A lo hecho, pecho."),
    ("You snooze, you lose.", "Camarón que se duerme, se lo lleva la corriente."),
    ("The shoemaker's son always goes barefoot.", "En casa del herrero, cuchillo de palo."),
    ("Easier said than done.", "Del dicho al hecho hay mucho trecho."),
    ("God squeezes, but He never chokes.", "Dios aprieta pero no ahoga."),
    ("Knowledge takes up no space.", "El saber no ocupa lugar."),
    ("There is none so blind as those who will not see.", "No hay peor ciego que el que no quiere ver."),
    ("Barking dogs seldom bite.", "Perro ladrador, poco mordedor."),
    ("To silly words, deaf ears.", "A palabras necias, oídos sordos."),
    ("A full belly makes a happy heart.", "Barriga llena, corazón contento."),
    ("Raise ravens and they'll peck your eyes out.", "Cría cuervos y te sacarán los ojos."),
    ("Today for you, tomorrow for me.", "Hoy por ti, mañana por mí."),
    ("Greed bursts the bag.", "La avaricia rompe el saco."),
    ("Hope is the last thing to be lost.", "La esperanza es lo último que se pierde."),
    ("United we stand, divided we fall.", "La unión hace la fuerza."),
    ("Buy cheap, buy twice.", "Lo barato sale caro."),
    ("Don't wash your dirty linen in public.", "Los trapos sucios se lavan en casa."),
    ("Never say never.", "Nunca digas nunca."),
    ("Deeds are love, not fine words.", "Obras son amores, que no buenas razones."),
    ("To each his own.", "Para gustos, colores."),
    ("Think the worst and you'll be right.", "Piensa mal y acertarás."),
    ("Grasp all, lose all.", "Quien mucho abarca, poco aprieta."),
    ("To correct a mistake is wise.", "Rectificar es de sabios."),
    ("The pitcher goes so often to the well that it breaks at last.", "Tanto va el cántaro a la fuente que al final se rompe."),
]

TECH = [
    ("There are only two hard things in computer science: cache invalidation and naming things.", "Hay solo dos cosas difíciles en informática: invalidar la caché y poner nombres."),
    ("It works on my machine.", "Funciona en mi máquina."),
    ("Have you tried turning it off and on again?", "¿Has probado a apagarlo y encenderlo de nuevo?"),
    ("Any sufficiently advanced technology is indistinguishable from magic.", "Cualquier tecnología suficientemente avanzada es indistinguible de la magia."),
    ("The best error message is the one that never appears.", "El mejor mensaje de error es el que nunca aparece."),
    ("A bug is never just a mistake. It represents something bigger.", "Un error nunca es solo un error. Representa algo más grande."),
    ("Programs must be written for people to read, and only incidentally for machines to execute.", "Los programas deben escribirse para que los lean personas, y solo de paso para que los ejecuten máquinas."),
    ("Simplicity is prerequisite for reliability.", "La simplicidad es requisito de la fiabilidad."),
    ("Before software can be reusable it first has to be usable.", "Para que el software sea reutilizable, primero debe ser utilizable."),
    ("The most dangerous phrase in the language is 'we've always done it this way.'", "La frase más peligrosa es 'siempre lo hemos hecho así'."),
    ("Measuring programming progress by lines of code is like measuring aircraft building progress by weight.", "Medir el progreso en líneas de código es como medir un avión por su peso."),
    ("First, solve the problem. Then, write the code.", "Primero resuelve el problema. Después escribe el código."),
    ("Code is like humor. When you have to explain it, it's bad.", "El código es como el humor: si hay que explicarlo, es malo."),
    ("Make it work, make it right, make it fast.", "Haz que funcione, hazlo bien, hazlo rápido."),
    ("Deleted code is debugged code.", "Código eliminado es código depurado."),
    ("If debugging is the process of removing bugs, then programming must be the process of putting them in.", "Si depurar es quitar errores, programar es ponerlos."),
    ("There are two ways to write error-free programs; only the third one works.", "Hay dos formas de escribir programas sin errores; solo la tercera funciona."),
    ("A good programmer is someone who always looks both ways before crossing a one-way street.", "Un buen programador mira a ambos lados antes de cruzar una calle de sentido único."),
    ("The code you write makes you a programmer. The code you delete makes you a good one.", "El código que escribes te hace programador; el que borras te hace bueno."),
    ("Don't comment bad code -- rewrite it.", "No comentes el mal código, reescríbelo."),
    ("It's not a bug, it's a feature.", "No es un error, es una función."),
    ("Weeks of coding can save you hours of planning.", "Semanas programando te ahorran horas de planificación."),
    ("There are only 10 kinds of people: those who understand binary and those who don't.", "Solo hay 10 tipos de personas: las que entienden binario y las que no."),
    ("A user interface is like a joke: if you have to explain it, it's not that good.", "Una interfaz es como un chiste: si hay que explicarla, no es buena."),
    ("Real programmers count from 0.", "Los programadores de verdad empiezan a contar desde 0."),
    ("The best thing about a boolean is even if you are wrong, you are only off by a bit.", "Lo mejor de un booleano es que si te equivocas, solo te equivocas por un bit."),
    ("Why do programmers prefer dark mode? Because light attracts bugs.", "¿Por qué los programadores prefieren el modo oscuro? Porque la luz atrae errores."),
    ("One man's crappy software is another man's full-time job.", "El software basura de uno es el trabajo fijo de otro."),
]


class Extension:
    def __init__(self, config):
        self.config = config or {}
        self._last_idx = None

    def _config_path(self):
        base = self.config.get("data_dir") or os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, "fortune_config.json")

    def _language(self):
        try:
            with open(self._config_path(), encoding="utf-8") as f:
                lang = json.load(f).get("language", "en")
        except Exception:
            return "en"
        return lang if lang in LANGS else "en"

    def get_config(self):
        return {"value": {"language": self._language(), "languages": list(LANGS)}}

    def set_language(self, data=None):
        data = data or {}
        lang = data.get("language", "")
        if lang not in LANGS:
            return {"error": "unsupported language"}
        try:
            os.makedirs(os.path.dirname(self._config_path()), exist_ok=True)
            with open(self._config_path(), "w", encoding="utf-8") as f:
                json.dump({"language": lang}, f)
        except OSError as e:
            return {"error": "could not save: %s" % e}
        out = {"language": lang}
        text = self._translate(data.get("current", ""), lang)
        if text is not None:
            out["text"] = text
        return {"value": out}

    def get_fortune(self):
        pool = FORTUNES + TECH
        idx = random.randrange(len(pool))
        while len(pool) > 1 and idx == self._last_idx:
            idx = random.randrange(len(pool))
        self._last_idx = idx
        return {"value": self._pick(pool[idx])}

    def _pick(self, pair):
        return pair[1] if self._language() == "es" else pair[0]

    def _translate(self, current, lang):
        if not current:
            return None
        for en, es in FORTUNES + TECH:
            if current == en or current == es:
                return es if lang == "es" else en
        return None
