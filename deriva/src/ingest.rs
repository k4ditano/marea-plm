//  Guardar algo. Es la operación que importa.
//
//  Una petición puede traer varias cosas —un lote de ficheros— y sale una
//  captura por cada una, con su resultado propio. Que el lote entero se
//  resuelva en un único «bien» o «mal» sería mentir en el caso normal: de
//  sesenta ficheros arrastrados, cincuenta y nueve nuevos y uno repetido no es
//  un fallo.
//
//  El orden de los pasos es el del plan y no es negociable:
//
//      identificar → hashear → mirar si ya estaba → escribir el blob →
//      confirmar en SQLite → indexar
//
//  El blob antes que la fila. Un corte entre ambos deja, como mucho, bytes sin
//  dueño en el disco; al revés dejaría una captura visible apuntando a un
//  fichero que no existe, y eso ya no se puede reparar leyendo la base.

use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};

//  Los tipos que se saben guardar. Cerrado a propósito: `type` acaba en la
//  interfaz decidiendo iconos y filtros, y una lista abierta significa que
//  cualquier cliente puede inventarse una categoría que la página no dibuja.
pub const TIPOS: &[&str] = &[
    "text", "url", "image", "document", "code", "video", "audio", "file",
];

//  El texto de una captura tiene tope. No es por el disco —SQLite se lo traga—
//  sino porque `content_text` entra entero en el índice de búsqueda y en cada
//  resultado que lo devuelve.
pub const TOPE_TEXTO: usize = 4 * 1024 * 1024;

#[derive(Debug, Deserialize, Default)]
pub struct Peticion {
    #[serde(rename = "type")]
    pub tipo: String,
    pub source_url: Option<String>,
    pub title: Option<String>,
    pub author: Option<String>,
    pub excerpt: Option<String>,
    pub note: Option<String>,
    pub text: Option<String>,
    //  Ficheros del disco del usuario. Una captura por cada uno.
    #[serde(default)]
    pub paths: Vec<String>,
    //  O los bytes en línea, para lo que no tiene fichero: una imagen
    //  arrastrada desde una página.
    pub inline: Option<EnLinea>,
    #[serde(default)]
    pub tags: Vec<String>,
    pub space: Option<String>,
    //  Para la reaparición: si viene, la captura nace dormida hasta esa fecha.
    pub snoozed_until: Option<i64>,
}

#[derive(Debug, Deserialize)]
pub struct EnLinea {
    pub mime: Option<String>,
    pub name: Option<String>,
    pub base64: String,
}

#[derive(Debug, Serialize)]
pub struct Resultado {
    pub status: String, //  saved · duplicate · rejected · failed
    #[serde(skip_serializing_if = "Option::is_none")]
    pub id: Option<String>,
    //  De qué dirección era, en lo que se guardó. La canónica si la hay.
    //
    //  Está aquí para que quien acaba de guardar pueda ir a por su portada sin
    //  volver a preguntar por la captura entera: sabe el id, pero el id no dice
    //  a qué página salir, y un `get` de vuelta para leer un campo que quien
    //  llama ya tenía en la mano es un viaje por nada.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub url: Option<String>,
    //  Y dónde ha quedado el fichero, por lo mismo: para poder abrirlo y
    //  sacarle el texto sin esperar al siguiente repaso. Un PDF que acabas de
    //  soltar tiene que poder buscarse por dentro esta misma tarde.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub duplicate_of: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

impl Resultado {
    fn guardado(id: String) -> Self {
        Resultado { status: "saved".into(), id: Some(id), url: None, path: None,
                    duplicate_of: None, reason: None }
    }
    fn duplicado(de: String) -> Self {
        Resultado { status: "duplicate".into(), id: None, url: None, path: None,
                    duplicate_of: Some(de), reason: None }
    }
    fn rechazado(por: &str) -> Self {
        Resultado {
            status: "rejected".into(),
            id: None,
            url: None,
            path: None,
            duplicate_of: None,
            reason: Some(por.into()),
        }
    }
    fn fallido(por: String) -> Self {
        Resultado { status: "failed".into(), id: None, url: None, path: None,
                    duplicate_of: None, reason: Some(por) }
    }
}

pub fn ingerir(db: &Connection, p: &Peticion) -> Vec<Resultado> {
    if !TIPOS.contains(&p.tipo.as_str()) {
        return vec![Resultado::rechazado("tipo_desconocido")];
    }
    let mut fuera = Vec::new();

    //  Los ficheros, uno por uno.
    for ruta in &p.paths {
        fuera.push(match una_de_fichero(db, p, ruta) {
            Ok(r) => r,
            Err(e) => Resultado::fallido(e),
        });
    }

    //  Y lo que no venía en un fichero: los bytes en línea o el texto. Solo si
    //  no había ficheros: un arrastre trae una cosa u otra, y guardar las dos
    //  duplicaría la misma captura con dos formas distintas.
    if p.paths.is_empty() {
        fuera.push(match una_suelta(db, p) {
            Ok(r) => r,
            Err(e) => Resultado::fallido(e),
        });
    }
    fuera
}

// ── una captura que viene de un fichero ──────────────────────────

fn una_de_fichero(db: &Connection, p: &Peticion, ruta: &str) -> Result<Resultado, String> {
    let real = match resolver(ruta) {
        Ok(r) => r,
        Err(e) => return Ok(Resultado::rechazado(e)),
    };
    let hash = crate::util::sha256_de_fichero(&real).map_err(|e| e.to_string())?;

    if let Some(id) = ya_estaba(db, None, None, Some(&hash)).map_err(|e| e.to_string())? {
        return Ok(Resultado::duplicado(id));
    }

    //  El blob primero.
    let g = crate::blobs::guardar_fichero(&real).map_err(|e| e.to_string())?;
    let nombre = real
        .file_name()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_default();
    //  El tipo, por la extensión. Es una PISTA para dibujar —¿enseño esto como
    //  una miniatura o como un icono?— y no una verdad sobre el contenido: lo
    //  real lo dice quien lo abra. Sin ella, una foto guardada desde el gestor
    //  de archivos se dibujaba con el icono de «fichero», que es la cosa más
    //  inútil que se puede poner encima de una foto.
    let mime = mime_por_extension(&nombre);
    let titulo = p.title.clone().unwrap_or_else(|| nombre.clone());

    let id = escribir(
        db,
        Nueva {
            tipo: &p.tipo,
            source_url: Some(&format!("file://{}", real.display())),
            canonical: None,
            title: &titulo,
            author: p.author.as_deref().unwrap_or(""),
            excerpt: p.excerpt.as_deref().unwrap_or(""),
            note: p.note.as_deref().unwrap_or(""),
            content_text: "",
            content_hash: None,
            blob_hash: Some(&g.hash),
            blob_bytes: Some(g.bytes as i64),
            blob_mime: mime,
            blob_name: Some(&nombre),
            snoozed_until: p.snoozed_until,
            tags: &p.tags,
            space: p.space.as_deref(),
            fuente: "",
        },
    )
    .map_err(|e| e.to_string())?;
    let mut r = Resultado::guardado(id);
    //  Dónde ha quedado, para poder mirar dentro sin esperar al siguiente
    //  repaso: un PDF recién soltado tiene que buscarse por dentro hoy.
    r.path = Some(crate::paths::blob_de(&g.hash).to_string_lossy().to_string());
    Ok(r)
}

//  Una ruta que se puede copiar, o el porqué de que no.
//
//  Los enlaces se resuelven ANTES de mirar nada: el plan lo pide, y sin eso un
//  enlace a `/etc/shadow` con nombre de foto se copiaría a la biblioteca con
//  toda la inocencia del mundo.
fn resolver(ruta: &str) -> Result<std::path::PathBuf, &'static str> {
    let bruta = std::path::Path::new(ruta.trim_start_matches("file://"));
    if !bruta.is_absolute() {
        return Err("ruta_relativa");
    }
    let real = std::fs::canonicalize(bruta).map_err(|_| "no_existe")?;
    let meta = std::fs::metadata(&real).map_err(|_| "no_existe")?;
    if !meta.is_file() {
        return Err("no_es_un_fichero");
    }
    if meta.len() > crate::blobs::TOPE_FICHERO {
        return Err("demasiado_grande");
    }
    //  Los sistemas de ficheros que no son ficheros. Copiar de `/proc` da
    //  tamaños de cero y contenido que cambia mientras lo lees.
    for prohibido in ["/proc", "/sys", "/dev"] {
        if real.starts_with(prohibido) {
            return Err("ruta_del_sistema");
        }
    }
    //  Y la biblioteca no se copia a sí misma.
    // Canonical paths on Windows have a verbatim prefix; compare both sides
    // in the same form. This also catches a library reached through a symlink.
    if std::fs::canonicalize(crate::paths::base()).is_ok_and(|base| real.starts_with(base)) {
        return Err("ya_es_de_la_biblioteca");
    }
    Ok(real)
}

// ── una captura que no viene de un fichero ───────────────────────

//  ¿El título que tiene es uno de los de apaño?
//
//  Hace falta para enriquecer: el título de la portada de la página puede pisar
//  «ejemplo.com», pero no puede pisar el que traía el arrastre —ese lo puso el
//  navegador leyendo la misma página— ni, desde luego, uno escrito a mano.
//
//  La forma de saberlo es volver a calcular el apaño y compararlo. Es más largo
//  que guardar un booleano en una columna, y es lo correcto: un booleano habría
//  que migrarlo, mantenerlo al día y creérselo, y esto no puede desincronizarse
//  con la regla porque ES la regla.
pub fn titulo_de_emergencia(titulo: &str, origen: Option<&str>, canonica: Option<&str>) -> bool {
    let t = titulo.trim();
    if t.is_empty() {
        return true;
    }
    let Some(u) = origen else {
        return false;
    };
    if !u.starts_with("http") {
        return false;
    }
    //  La dirección tal cual, en cualquiera de sus dos formas.
    if t == u || canonica == Some(t) {
        return true;
    }
    //  Y lo que sacaría hoy el adaptador de esa misma URL: el dominio, el slug
    //  del hilo, «@usuario», «dueño/repo», el nombre del fichero.
    crate::adaptadores::leer(u).titulo.as_deref() == Some(t)
}

fn una_suelta(db: &Connection, p: &Peticion) -> Result<Resultado, String> {
    //  De qué sitio viene. Sin salir a la red: es todo lo que se puede saber
    //  mirando la URL, y es bastante. Lo que hace falta traer de fuera —el
    //  título de verdad, la miniatura— lo trae el lado de la casa, que es quien
    //  tiene la armadura anti-SSRF escrita y revisada.
    let leido = p
        .source_url
        .as_deref()
        .filter(|u| u.starts_with("http"))
        .map(crate::adaptadores::leer);

    //  La canónica del adaptador MANDA sobre la genérica: `youtu.be/ID` y
    //  `youtube.com/watch?v=ID&t=90` son el mismo vídeo, y la regla general no
    //  puede saberlo. Sin esto, el mismo vídeo desde el móvil y desde el
    //  escritorio son dos capturas y el duplicado no lo ve.
    let canonical = leido
        .as_ref()
        .and_then(|l| l.canonica.clone())
        .or_else(|| p.source_url.as_deref().and_then(crate::util::canonizar_url));
    let texto = p.text.as_deref().unwrap_or("");
    if texto.len() > TOPE_TEXTO {
        return Ok(Resultado::rechazado("texto_demasiado_largo"));
    }

    //  Los bytes en línea, si los hay.
    let mut blob: Option<crate::blobs::Guardado> = None;
    if let Some(en_linea) = &p.inline {
        let datos = match crate::util::base64(&en_linea.base64) {
            Some(d) => d,
            None => return Ok(Resultado::rechazado("base64_invalido")),
        };
        if datos.is_empty() {
            return Ok(Resultado::rechazado("sin_datos"));
        }
        if datos.len() > crate::blobs::TOPE_EN_LINEA {
            return Ok(Resultado::rechazado("demasiado_grande"));
        }
        let hash = crate::util::sha256(&datos);
        if let Some(id) =
            ya_estaba(db, canonical.as_deref(), None, Some(&hash)).map_err(|e| e.to_string())?
        {
            return Ok(Resultado::duplicado(id));
        }
        blob = Some(crate::blobs::guardar_bytes(&datos).map_err(|e| e.to_string())?);
    }

    let content_hash = if texto.trim().is_empty() {
        None
    } else {
        Some(crate::util::hash_de_texto(texto))
    };

    //  Nada que guardar no es un fallo, es que no había nada.
    if blob.is_none() && content_hash.is_none() && canonical.is_none() {
        return Ok(Resultado::rechazado("sin_contenido"));
    }

    if let Some(id) = ya_estaba(db, canonical.as_deref(), content_hash.as_deref(), None)
        .map_err(|e| e.to_string())?
    {
        return Ok(Resultado::duplicado(id));
    }

    //  El título por defecto: el que diga el adaptador, la primera línea del
    //  texto, o la URL. En ese orden, porque «@usuario» o «dueño/repo» dicen
    //  más que una dirección entera, y una dirección entera dice más que nada.
    let titulo = p.title.clone().unwrap_or_else(|| {
        leido
            .as_ref()
            .and_then(|l| l.titulo.clone())
            .or_else(|| texto.lines().next().map(|l| recortar(l, 120)))
            .or_else(|| canonical.clone())
            .unwrap_or_default()
    });
    //  Y el extracto, si nadie lo trae, del principio del texto. Sirve para la
    //  tarjeta sin tener que leer `content_text` entero.
    let extracto = p
        .excerpt
        .clone()
        .unwrap_or_else(|| recortar(texto.trim(), 280));

    //  El tipo del adaptador manda solo sobre el genérico. Si quien ingiere ya
    //  dijo «documento», sabe más que nosotros; si dijo «url», es lo que dice
    //  cualquier arrastre de un enlace, y ahí el adaptador sí sabe más: un
    //  enlace de YouTube es un vídeo aunque la URL no acabe en `.mp4`.
    let tipo = leido
        .as_ref()
        .filter(|_| p.tipo == "url")
        .map(|l| l.fuente.tipo.to_string())
        .unwrap_or_else(|| p.tipo.clone());
    let fuente = leido.as_ref().map(|l| l.fuente.id).unwrap_or("");

    let g = blob.as_ref();
    let id = escribir(
        db,
        Nueva {
            tipo: &tipo,
            source_url: p.source_url.as_deref(),
            canonical: canonical.as_deref(),
            title: &titulo,
            author: p.author.as_deref().unwrap_or(""),
            excerpt: &extracto,
            note: p.note.as_deref().unwrap_or(""),
            content_text: texto,
            content_hash: content_hash.as_deref(),
            blob_hash: g.map(|x| x.hash.as_str()),
            blob_bytes: g.map(|x| x.bytes as i64),
            blob_mime: p.inline.as_ref().and_then(|x| x.mime.as_deref()),
            blob_name: p.inline.as_ref().and_then(|x| x.name.as_deref()),
            snoozed_until: p.snoozed_until,
            tags: &p.tags,
            space: p.space.as_deref(),
            fuente: fuente,
        },
    )
    .map_err(|e| e.to_string())?;
    let mut r = Resultado::guardado(id);
    //  La canónica antes que la de origen: es la que hay que visitar, y la de
    //  origen puede traer media línea de parámetros de campaña.
    r.url = canonical.clone().or_else(|| p.source_url.clone());
    Ok(r)
}

//  Lo justo para saber si se puede enseñar. Cerrado a propósito: no es un
//  detector de tipos, es la lista de lo que esta interfaz sabe dibujar.
fn mime_por_extension(nombre: &str) -> Option<&'static str> {
    let n = nombre.to_lowercase();
    let ext = n.rsplit_once('.').map(|(_, e)| e.to_string()).unwrap_or_default();
    Some(match ext.as_str() {
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "webp" => "image/webp",
        "gif" => "image/gif",
        "avif" => "image/avif",
        "bmp" => "image/bmp",
        "pdf" => "application/pdf",
        "mp4" => "video/mp4",
        "webm" => "video/webm",
        "mkv" => "video/x-matroska",
        "mp3" => "audio/mpeg",
        "flac" => "audio/flac",
        "opus" | "ogg" => "audio/ogg",
        "txt" | "md" => "text/plain",
        _ => return None,
    })
}

fn recortar(s: &str, n: usize) -> String {
    //  Por caracteres y no por bytes: cortar un UTF-8 por la mitad revienta.
    let mut fuera: String = s.chars().take(n).collect();
    if s.chars().count() > n {
        fuera.push('…');
    }
    fuera
}

// ── lo que ya estaba ─────────────────────────────────────────────
//
//  El plan: «existe el mismo `canonical_url` o hash». Los tres en un sitio, y
//  en este orden: la URL manda sobre el contenido porque la misma página
//  cambia de texto entre visitas y sigue siendo la misma página.
//
//  Lo tirado a la basura no cuenta. Volver a guardar algo que borraste tiene
//  que funcionar, o el borrado sería una condena.
fn ya_estaba(
    db: &Connection,
    canonical: Option<&str>,
    content_hash: Option<&str>,
    blob_hash: Option<&str>,
) -> rusqlite::Result<Option<String>> {
    for (columna, valor) in [
        ("canonical_url", canonical),
        ("content_hash", content_hash),
        ("blob_hash", blob_hash),
    ] {
        let Some(v) = valor else { continue };
        if v.is_empty() {
            continue;
        }
        let sql = format!(
            "SELECT id FROM captures WHERE {} = ?1 AND trashed_at IS NULL LIMIT 1",
            columna
        );
        if let Some(id) = db.query_row(&sql, [v], |r| r.get::<_, String>(0)).optional()? {
            return Ok(Some(id));
        }
    }
    Ok(None)
}

// ── escribir la fila ─────────────────────────────────────────────

struct Nueva<'a> {
    tipo: &'a str,
    source_url: Option<&'a str>,
    canonical: Option<&'a str>,
    title: &'a str,
    author: &'a str,
    excerpt: &'a str,
    note: &'a str,
    content_text: &'a str,
    content_hash: Option<&'a str>,
    blob_hash: Option<&'a str>,
    blob_bytes: Option<i64>,
    blob_mime: Option<&'a str>,
    blob_name: Option<&'a str>,
    snoozed_until: Option<i64>,
    tags: &'a [String],
    space: Option<&'a str>,
    //  De qué sitio viene, del adaptador. Vacío para lo que no sale de una URL.
    fuente: &'a str,
}

fn escribir(db: &Connection, n: Nueva) -> rusqlite::Result<String> {
    let id = crate::util::nuevo_id();
    //  Todo en una transacción: la fila, sus etiquetas, su espacio y su índice.
    //  Una captura a medias —guardada pero sin indexar— es una captura que no
    //  se puede encontrar, que a efectos del usuario es una captura perdida.
    let tx = db.unchecked_transaction()?;
    tx.execute(
        "INSERT INTO captures
           (id, type, source_url, canonical_url, title, author, excerpt, note,
            content_text, content_hash, blob_hash, blob_bytes, blob_mime, blob_name,
            status, captured_at, snoozed_until, source)
         VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14,?15,?16,?17,?18)",
        params![
            id,
            n.tipo,
            n.source_url,
            n.canonical,
            n.title,
            n.author,
            n.excerpt,
            n.note,
            n.content_text,
            n.content_hash,
            n.blob_hash,
            n.blob_bytes,
            n.blob_mime,
            n.blob_name,
            "saved",
            crate::util::ahora_ms(),
            n.snoozed_until,
            n.fuente,
        ],
    )?;
    for t in n.tags {
        poner_etiqueta(&tx, &id, t)?;
    }
    if let Some(s) = n.space {
        poner_espacio(&tx, &id, s)?;
    }
    crate::db::reindexar(&tx, &id)?;
    tx.commit()?;
    Ok(id)
}

pub fn poner_etiqueta(db: &Connection, capture: &str, nombre: &str) -> rusqlite::Result<()> {
    let limpio = nombre.trim().to_lowercase();
    if limpio.is_empty() {
        return Ok(());
    }
    //  La etiqueta se crea si no estaba. El id es el propio nombre normalizado:
    //  dos etiquetas con el mismo nombre son la misma etiqueta, y con un id
    //  aleatorio harían falta comprobaciones en cada sitio que las escribe.
    db.execute(
        "INSERT OR IGNORE INTO tags (id, name) VALUES (?1, ?1)",
        [&limpio],
    )?;
    db.execute(
        "INSERT OR IGNORE INTO capture_tags (capture_id, tag_id) VALUES (?1, ?2)",
        params![capture, limpio],
    )?;
    Ok(())
}

//  El identificador de una carpeta a partir de su nombre.
//
//  Minúsculas, sin acentos y con guiones: «Cosas de casa» → `cosas-de-casa`.
//  Hace falta porque el id viaja en el filtro de la página y en las órdenes de
//  la línea de comandos, y un id con espacios y tildes es un id que hay que
//  escapar en cada sitio por el que pasa.
//
//  Y una vez puesto NO cambia aunque se renombre la carpeta: es lo que hace que
//  renombrar sea renombrar y no crear otra.
pub fn id_de_espacio(nombre: &str) -> String {
    let mut fuera = String::new();
    let mut guion = false;
    for c in nombre.trim().to_lowercase().chars() {
        let c = match c {
            'á' | 'à' | 'ä' | 'â' => 'a',
            'é' | 'è' | 'ë' | 'ê' => 'e',
            'í' | 'ì' | 'ï' | 'î' => 'i',
            'ó' | 'ò' | 'ö' | 'ô' => 'o',
            'ú' | 'ù' | 'ü' | 'û' => 'u',
            'ñ' => 'n',
            'ç' => 'c',
            otro => otro,
        };
        if c.is_ascii_alphanumeric() {
            fuera.push(c);
            guion = false;
        } else if !guion && !fuera.is_empty() {
            fuera.push('-');
            guion = true;
        }
    }
    while fuera.ends_with('-') {
        fuera.pop();
    }
    fuera.chars().take(48).collect()
}

//  Mete una captura en una carpeta, y crea la carpeta si no estaba.
//
//  Acepta el id o el nombre: quien llama desde la página manda el id que sacó
//  de la lista, y quien llama desde una herramienta de la IA manda «leer luego»
//  porque es lo que ha escrito una persona. Los dos tienen que funcionar, y
//  probar primero por id es lo que evita que «Leer luego» cree una carpeta
//  nueva al lado de la que ya existe.
pub fn poner_espacio(db: &Connection, capture: &str, nombre: &str) -> rusqlite::Result<()> {
    let limpio = nombre.trim();
    if limpio.is_empty() {
        return Ok(());
    }
    let id = id_de_espacio(limpio);
    if id.is_empty() {
        return Ok(());
    }
    //  Si ya hay una carpeta con ese id, se usa esa y se respeta su nombre: al
    //  revés, mover algo a «leer-luego» le cambiaría el nombre a «leer-luego».
    db.execute(
        "INSERT OR IGNORE INTO spaces (id, name) VALUES (?1, ?2)",
        params![id, limpio],
    )?;
    db.execute(
        "INSERT OR IGNORE INTO capture_spaces (capture_id, space_id) VALUES (?1, ?2)",
        params![capture, id],
    )?;
    Ok(())
}
