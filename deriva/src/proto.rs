//  El protocolo, y el sitio único donde se decide qué hace cada método.
//
//  JSON Lines versionado, como el del agente y por los mismos motivos: una
//  línea es un mensaje, el canal de datos es solo stdout —los avisos van a
//  stderr, o una traza se convierte en un mensaje mal formado, o peor, en uno
//  que parece válido— y hay tope de línea, porque sin tope el búfer del que lee
//  crece con lo que diga el otro lado.
//
//  El mismo despachador atiende el socket y la línea de órdenes. Dos caminos
//  distintos hacia la misma base es como se acaba teniendo dos comportamientos
//  para lo mismo y una prueba que solo cubre uno.

use rusqlite::Connection;
use serde::{Deserialize, Serialize};

//  Lo que puede pesar una miniatura que llega de fuera. Medio mega es el mismo
//  tope que pone `tools/web` al traerla; repetirlo aquí no es desconfianza de
//  esa herramienta, es que este proceso no sabe quién le está escribiendo.
const TOPE_MINIATURA: usize = 512 * 1024;

pub const VERSION: u32 = 1;
//  Lo más gordo que puede viajar en una línea: una imagen en línea de 64 MiB
//  en base64 crece un tercio, más el resto del mensaje.
pub const TOPE_LINEA: usize = 90 * 1024 * 1024;

#[derive(Debug, Deserialize)]
pub struct Peticion {
    #[serde(default)]
    pub v: u32,
    #[serde(default)]
    pub id: String,
    pub method: String,
    #[serde(default)]
    pub params: serde_json::Value,
}

#[derive(Debug, Serialize)]
pub struct Respuesta {
    pub v: u32,
    pub id: String,
    pub ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<Error>,
}

#[derive(Debug, Serialize)]
pub struct Error {
    pub code: String,
    pub message: String,
}

impl Respuesta {
    pub fn bien(id: &str, r: serde_json::Value) -> Self {
        Respuesta { v: VERSION, id: id.into(), ok: true, result: Some(r), error: None }
    }
    pub fn mal(id: &str, code: &str, message: impl Into<String>) -> Self {
        Respuesta {
            v: VERSION,
            id: id.into(),
            ok: false,
            result: None,
            error: Some(Error { code: code.into(), message: message.into() }),
        }
    }
}

//  Lo que se puede pedir. Cerrado, y sin ninguno que reciba una ruta libre
//  salvo `export`: el plan lo dice —«no se aceptan rutas arbitrarias en los
//  métodos del agente»— y exportar es la excepción porque la ruta la elige el
//  usuario y la valida el controlador antes de llegar aquí.
pub fn despachar(db: &Connection, p: &Peticion) -> Respuesta {
    if p.v != 0 && p.v != VERSION {
        return Respuesta::mal(&p.id, "version", format!("solo hablo la v{}", VERSION));
    }
    match p.method.as_str() {
        "ping" => Respuesta::bien(
            &p.id,
            serde_json::json!({ "pong": true, "schema": crate::db::VERSION }),
        ),

        "ingest" => match serde_json::from_value::<crate::ingest::Peticion>(p.params.clone()) {
            Ok(pet) => {
                let items = crate::ingest::ingerir(db, &pet);
                let guardadas = items.iter().filter(|r| r.status == "saved").count();
                let duplicadas = items.iter().filter(|r| r.status == "duplicate").count();
                Respuesta::bien(
                    &p.id,
                    serde_json::json!({
                        "items": items, "saved": guardadas, "duplicates": duplicadas,
                    }),
                )
            }
            Err(e) => Respuesta::mal(&p.id, "params", e.to_string()),
        },

        "search" => {
            let q = p.params.get("query").and_then(|v| v.as_str()).unwrap_or("");
            let n = p.params.get("limit").and_then(|v| v.as_u64()).unwrap_or(20) as usize;
            match crate::search::buscar(db, q, n) {
                Ok(items) => Respuesta::bien(&p.id, serde_json::json!({ "items": items })),
                Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
            }
        }

        "list" => {
            let n = p.params.get("limit").and_then(|v| v.as_u64()).unwrap_or(50) as usize;
            let desde = p.params.get("before").and_then(|v| v.as_i64());
            let f: crate::search::Filtro =
                serde_json::from_value(p.params.clone()).unwrap_or_default();
            match crate::search::listar(db, n, desde, &f) {
                Ok(items) => Respuesta::bien(&p.id, serde_json::json!({ "items": items })),
                Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
            }
        }

        //  Lo que la página necesita de una vez al abrirse: la navegación con
        //  sus números, lo que ha vuelto a la superficie y la primera página de
        //  la biblioteca. Tres viajes por el socket para pintar una pantalla es
        //  tres oportunidades de pintarla a medias.
        "home" => {
            let n = p.params.get("limit").and_then(|v| v.as_u64()).unwrap_or(60) as usize;
            let f: crate::search::Filtro =
                serde_json::from_value(p.params.clone()).unwrap_or_default();
            let r = (|| -> rusqlite::Result<serde_json::Value> {
                Ok(serde_json::json!({
                    "sections": crate::search::secciones(db)?,
                    //  Con su porqué. Todas las de aquí volvieron por la misma
                    //  razón —las aplazaste y ya toca—, pero la página lo
                    //  enseña, y una razón que hay que adivinar mirando el
                    //  código no la enseña nadie.
                    "surfaced": crate::search::reaparecidas(db, 3)?
                        .into_iter()
                        .map(|f| {
                            let mut v = serde_json::to_value(f).unwrap_or_default();
                            if let Some(o) = v.as_object_mut() {
                                o.insert("porque".into(),
                                         serde_json::json!("la aplazaste para hoy"));
                            }
                            v
                        })
                        .collect::<Vec<_>>(),
                    "items": crate::search::listar(db, n, None, &f)?,
                    "stats": crate::search::cuentas(db)?,
                }))
            })();
            match r {
                Ok(v) => Respuesta::bien(&p.id, v),
                Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
            }
        }

        //  ── las carpetas ─────────────────────────────────────────
        //
        //  Hasta ahora una carpeta solo existía si le metías algo dentro: se
        //  creaba de camino, en `poner_espacio`. Eso vale para las tres de
        //  fábrica y no vale para las tuyas, porque las tuyas se hacen ANTES de
        //  tener qué meter —«voy a tener una de la mudanza»— y porque una
        //  carpeta que desaparece al sacar lo último no es una carpeta.
        //
        //  El id se saca del nombre y NO cambia al renombrar: es lo que hace
        //  que renombrar sea renombrar y no crear otra al lado.
        "space_put" => {
            let nombre = p
                .params
                .get("name")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .trim()
                .chars()
                .take(60)
                .collect::<String>();
            if nombre.is_empty() {
                return Respuesta::mal(&p.id, "sin_nombre", "una carpeta necesita un nombre");
            }
            //  Con id se renombra la que hay; sin él se crea una nueva.
            let id = p
                .params
                .get("id")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string())
                .unwrap_or_else(|| crate::ingest::id_de_espacio(&nombre));
            if id.is_empty() {
                return Respuesta::mal(&p.id, "nombre_invalido",
                                      "de ese nombre no sale ningún identificador");
            }
            let color = p
                .params
                .get("color")
                .and_then(|v| v.as_str())
                .filter(|c| c.starts_with('#') && c.len() <= 9)
                .unwrap_or("");
            let r = db.execute(
                "INSERT INTO spaces (id, name, color) VALUES (?1, ?2, ?3)
                 ON CONFLICT(id) DO UPDATE SET name = ?2,
                     color = CASE WHEN ?3 = '' THEN color ELSE ?3 END",
                rusqlite::params![id, nombre, color],
            );
            match r {
                Ok(_) => Respuesta::bien(
                    &p.id,
                    serde_json::json!({ "id": id, "name": nombre }),
                ),
                Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
            }
        }

        //  Y quitarla. Lo de dentro NO se borra: se queda en la biblioteca sin
        //  carpeta, que es lo que espera cualquiera que haya borrado una
        //  carpeta en su vida. Borrar una estantería no quema los libros.
        "space_delete" => {
            let id = p.params.get("id").and_then(|v| v.as_str()).unwrap_or("");
            if id.is_empty() {
                return Respuesta::mal(&p.id, "sin_id", "hay que decir cuál");
            }
            let sueltas = db
                .execute("DELETE FROM capture_spaces WHERE space_id = ?1", [id])
                .unwrap_or(0);
            match db.execute("DELETE FROM spaces WHERE id = ?1", [id]) {
                Ok(0) => Respuesta::mal(&p.id, "no_existe", "no hay ninguna carpeta con ese id"),
                Ok(_) => Respuesta::bien(
                    &p.id,
                    serde_json::json!({ "id": id, "released": sueltas }),
                ),
                Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
            }
        }

        //  Las etiquetas que ya usas, con cuántas cosas tienen cada una.
        //
        //  La sección «Etiquetas» solo llevaba el número, así que no había
        //  manera de saber cuáles son. Hace falta para dos cosas: enseñarlas, y
        //  poder decirle a la IA «usa estas» —sin eso estrena taxonomía en cada
        //  tanda y a la semana hay doscientas etiquetas de una captura cada
        //  una—.
        "tags" => {
            let r = (|| -> rusqlite::Result<Vec<serde_json::Value>> {
                let mut s = db.prepare(
                    "SELECT t.name, COUNT(ct.capture_id)
                       FROM tags t
                       LEFT JOIN capture_tags ct ON ct.tag_id = t.id
                       LEFT JOIN captures c ON c.id = ct.capture_id AND c.trashed_at IS NULL
                      GROUP BY t.id
                      HAVING COUNT(c.id) > 0
                      ORDER BY COUNT(c.id) DESC, t.name
                      LIMIT 200",
                )?;
                let v = s
                    .query_map([], |r| {
                        Ok(serde_json::json!({
                            "name": r.get::<_, String>(0)?,
                            "count": r.get::<_, i64>(1)?,
                        }))
                    })?
                    .filter_map(|x| x.ok())
                    .collect();
                Ok(v)
            })();
            match r {
                Ok(v) => Respuesta::bien(&p.id, serde_json::json!({ "tags": v })),
                Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
            }
        }

        "sections" => match crate::search::secciones(db) {
            Ok(v) => Respuesta::bien(&p.id, serde_json::json!({ "sections": v })),
            Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
        },

        //  Aplazar: vuelve a la superficie cuando toque. La fecha la calcula
        //  quien la pide; aquí solo se guarda, porque «dentro de una semana»
        //  depende de un calendario y esto no tiene ninguno.
        "snooze" => {
            let id = p.params.get("id").and_then(|v| v.as_str()).unwrap_or("");
            let hasta = p.params.get("until").and_then(|v| v.as_i64());
            match db.execute(
                "UPDATE captures SET snoozed_until = ?2 WHERE id = ?1",
                rusqlite::params![id, hasta],
            ) {
                Ok(0) => Respuesta::mal(&p.id, "no_existe", "no hay ninguna con ese id"),
                Ok(_) => Respuesta::bien(&p.id, serde_json::json!({ "id": id })),
                Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
            }
        }

        //  La nota personal, las etiquetas y el favorito: lo único que la
        //  página escribe de una captura. El contenido no se edita —lo que
        //  guardaste es lo que había—, y por eso no hay un método para tocarlo.
        "annotate" => {
            let id = p.params.get("id").and_then(|v| v.as_str()).unwrap_or("");
            if crate::search::una(db, id).ok().flatten().is_none() {
                return Respuesta::mal(&p.id, "no_existe", "no hay ninguna con ese id");
            }
            if let Some(n) = p.params.get("note").and_then(|v| v.as_str()) {
                if let Err(e) = db.execute(
                    "UPDATE captures SET note = ?2 WHERE id = ?1",
                    rusqlite::params![id, &n.chars().take(4000).collect::<String>()],
                ) {
                    return Respuesta::mal(&p.id, "db", e.to_string());
                }
            }
            //  Que la has abierto. Es lo que hace que deje de volver: la regla
            //  de reaparición descarta lo que has mirado hace poco, y sin esto
            //  no habría manera de que se enterara.
            if p.params.get("opened").and_then(|v| v.as_bool()) == Some(true) {
                let _ = db.execute(
                    "UPDATE captures SET last_opened_at = ?2 WHERE id = ?1",
                    rusqlite::params![id, crate::util::ahora_ms()],
                );
            }
            if let Some(f) = p.params.get("favorite").and_then(|v| v.as_bool()) {
                let _ = db.execute(
                    "UPDATE captures SET favorite = ?2 WHERE id = ?1",
                    rusqlite::params![id, if f { 1 } else { 0 }],
                );
            }
            if let Some(ts) = p.params.get("tags").and_then(|v| v.as_array()) {
                let _ = db.execute("DELETE FROM capture_tags WHERE capture_id = ?1", [id]);
                for t in ts.iter().filter_map(|x| x.as_str()).take(32) {
                    let _ = crate::ingest::poner_etiqueta(db, id, t);
                }
            }
            if let Some(e) = p.params.get("space").and_then(|v| v.as_str()) {
                let _ = db.execute("DELETE FROM capture_spaces WHERE capture_id = ?1", [id]);
                if !e.is_empty() {
                    let _ = crate::ingest::poner_espacio(db, id, e);
                }
            }
            //  Y el vector, que describe lo mismo que el índice: si cambia el
            //  título o el resumen, lo que la captura «quiere decir» cambia con
            //  ellos. Rehacerlo aquí es lo que evita tener dos verdades.
            let _ = crate::search::revectorizar(db, id);

            match crate::db::reindexar(db, id) {
                Ok(()) => match crate::search::una(db, id) {
                    Ok(Some(f)) => Respuesta::bien(&p.id, serde_json::json!({ "item": f })),
                    _ => Respuesta::mal(&p.id, "db", "no se pudo releer"),
                },
                Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
            }
        }

        //  Lo que sigue sin portada, para ir a buscarla. Ver
        //  `search::por_enriquecer`.
        "to_enrich" => {
            let n = p
                .params
                .get("limit")
                .and_then(|v| v.as_i64())
                .unwrap_or(12)
                .clamp(1, 60);
            match crate::search::por_enriquecer(db, n) {
                Ok(v) => Respuesta::bien(&p.id, serde_json::json!({ "items": v })),
                Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
            }
        }

        //  ── lo que se sabe de fuera ──────────────────────────────
        //
        //  El título de verdad, quién lo hizo y la miniatura. NO lo trae el
        //  worker: aquí no hay red y no la va a haber. Lo trae la casa con
        //  `tools/web`, que es donde viven las reglas anti-SSRF ya revisadas, y
        //  entra por aquí ya leído.
        //
        //  La regla de qué se pisa y qué no es lo importante de este método:
        //
        //  NUNCA pisa lo tuyo. La nota, las etiquetas, el favorito y el espacio
        //  no se tocan, y ni siquiera se leen.
        //
        //  Y el título solo si el que hay es de emergencia. Al guardar, un
        //  enlace se titula con lo que se pueda sacar de la propia dirección
        //  —el dominio, el slug—; eso es un apaño hasta que llegue el de
        //  verdad. Pero si al soltarlo el arrastre traía un título —y un
        //  navegador lo trae—, ese lo puso el sitio de donde venía y vale igual
        //  que este. Distinguirlos es la única manera de que enriquecer no sea
        //  un «pisa lo que había» con otro nombre.
        "enrich" => {
            let id = p.params.get("id").and_then(|v| v.as_str()).unwrap_or("");
            let Ok(Some(antes)) = crate::search::una(db, id) else {
                return Respuesta::mal(&p.id, "no_existe", "no hay ninguna con ese id");
            };
            let dice = |k: &str| -> String {
                p.params
                    .get(k)
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .trim()
                    .to_string()
            };

            //  La miniatura se comprueba ANTES de escribir nada.
            //
            //  Al revés —validándola donde se guarda— una foto ilegible dejaba
            //  el título y el autor ya escritos y devolvía un error: quien
            //  llama lo reintenta, y lo que hay guardado no es ni lo de antes
            //  ni lo de después.
            let foto = dice("preview_b64");
            let bytes_foto = if foto.is_empty() {
                None
            } else {
                match crate::util::base64(&foto) {
                    Some(b) if !b.is_empty() && b.len() <= TOPE_MINIATURA => Some(b),
                    _ => {
                        return Respuesta::mal(
                            &p.id,
                            "miniatura_invalida",
                            "la miniatura no se puede leer o pasa del tope",
                        )
                    }
                }
            };

            //  Y de paso, de qué sitio era.
            //
            //  Lo guardado antes de que existieran los adaptadores no tiene
            //  `source`, y eso no se arregla solo: se saca de la propia
            //  dirección, sin red, exactamente igual que al guardar. Se hace
            //  aquí porque este es el momento en que alguien vuelve a mirar una
            //  captura vieja; recorrer la biblioteca entera en la migración
            //  habría sido leer cien mil filas por si acaso.
            if antes.source.is_empty() {
                if let Some(u) = antes
                    .canonical_url
                    .as_deref()
                    .or(antes.source_url.as_deref())
                    .filter(|u| u.starts_with("http"))
                {
                    let l = crate::adaptadores::leer(u);
                    let _ = db.execute(
                        "UPDATE captures SET source = ?2 WHERE id = ?1",
                        rusqlite::params![id, l.fuente.id],
                    );
                    //  Y el tipo, solo si era el genérico: un enlace de YouTube
                    //  es un vídeo. Si ya decía otra cosa, alguien sabía más.
                    if antes.tipo == "url" {
                        let _ = db.execute(
                            "UPDATE captures SET type = ?2 WHERE id = ?1",
                            rusqlite::params![id, l.fuente.tipo],
                        );
                    }
                }
            }

            let titulo = dice("title");
            if !titulo.is_empty()
                && crate::ingest::titulo_de_emergencia(
                    &antes.title,
                    antes.source_url.as_deref(),
                    antes.canonical_url.as_deref(),
                )
            {
                let _ = db.execute(
                    "UPDATE captures SET title = ?2 WHERE id = ?1",
                    rusqlite::params![id, &titulo.chars().take(300).collect::<String>()],
                );
            }
            //  El autor y el resumen solo si están vacíos: ahí no hay nada que
            //  pisar, y si hay algo lo puso alguien que sabía más.
            let autor = dice("author");
            if !autor.is_empty() && antes.author.is_empty() {
                let _ = db.execute(
                    "UPDATE captures SET author = ?2 WHERE id = ?1",
                    rusqlite::params![id, &autor.chars().take(160).collect::<String>()],
                );
            }
            let resumen = dice("excerpt");
            if !resumen.is_empty() && antes.excerpt.is_empty() {
                let _ = db.execute(
                    "UPDATE captures SET excerpt = ?2 WHERE id = ?1",
                    rusqlite::params![id, &resumen.chars().take(600).collect::<String>()],
                );
            }
            //  Y el texto de dentro: el cuerpo de la página o lo que se haya
            //  podido sacar del fichero.
            //
            //  Solo si no había, y esa es la regla de siempre. Pero aquí tiene
            //  un motivo extra: el contenido es lo que se guardó, y una captura
            //  cuyo texto cambia sola deja de ser una copia de lo que viste.
            //  Volver a leer la página dentro de un mes traería otra cosa.
            //
            //  Va al índice, que es para lo que se lee: sin esto, buscar una
            //  frase de dentro de un artículo que guardaste no encuentra nada,
            //  y la biblioteca solo sabe de títulos.
            let cuerpo = dice("text");
            if !cuerpo.is_empty()
                && antes.excerpt.len() < crate::ingest::TOPE_TEXTO
                && cuerpo.len() <= crate::ingest::TOPE_TEXTO
            {
                let vacio: i64 = db
                    .query_row(
                        "SELECT COUNT(*) FROM captures WHERE id = ?1 AND content_text = ''",
                        [id],
                        |r| r.get(0),
                    )
                    .unwrap_or(0);
                if vacio == 1 {
                    //  Y vuelve a la cola de la IA —`summary_at = NULL`—: se
                    //  miró con lo que había entonces, a lo mejor solo un
                    //  título, y ahora hay un artículo entero. Es la única vez
                    //  que se descarta un intento, y es porque el material que
                    //  se miró ya no es el mismo.
                    let _ = db.execute(
                        "UPDATE captures SET content_text = ?2, content_hash = ?3,
                                summary_at = NULL
                          WHERE id = ?1",
                        rusqlite::params![id, &cuerpo, crate::util::hash_de_texto(&cuerpo)],
                    );
                    //  Y si no había extracto, el principio del texto sirve: es
                    //  lo que se enseña en la tarjeta y lo que ve el modelo.
                    if antes.excerpt.is_empty() {
                        let _ = db.execute(
                            "UPDATE captures SET excerpt = ?2 WHERE id = ?1",
                            rusqlite::params![
                                id,
                                cuerpo.trim().chars().take(280).collect::<String>()
                            ],
                        );
                    }
                }
            }

            //  Y la canónica, que es la que decide los duplicados. Solo si no
            //  había: cambiarla después movería a qué se parece esto.
            let canonica = dice("canonical_url");
            if !canonica.is_empty() && antes.canonical_url.is_none() {
                if let Some(c) = crate::util::canonizar_url(&canonica) {
                    let _ = db.execute(
                        "UPDATE captures SET canonical_url = ?2 WHERE id = ?1",
                        rusqlite::params![id, c],
                    );
                }
            }

            //  Y la miniatura al almacén de siempre, por su hash: la misma
            //  portada en veinte capturas ocupa una vez.
            if let Some(bytes) = bytes_foto {
                if antes.preview_path.is_none() {
                    match crate::blobs::guardar_bytes(&bytes) {
                        Ok(g) => {
                            let _ = db.execute(
                                "UPDATE captures SET preview_hash = ?2 WHERE id = ?1",
                                rusqlite::params![id, g.hash],
                            );
                        }
                        Err(e) => return Respuesta::mal(&p.id, "disco", e.to_string()),
                    }
                }
            }

            //  Y el vector, que describe lo mismo que el índice: si cambia el
            //  título o el resumen, lo que la captura «quiere decir» cambia con
            //  ellos. Rehacerlo aquí es lo que evita tener dos verdades.
            let _ = crate::search::revectorizar(db, id);

            match crate::db::reindexar(db, id) {
                Ok(()) => match crate::search::una(db, id) {
                    Ok(Some(f)) => Respuesta::bien(&p.id, serde_json::json!({ "item": f })),
                    _ => Respuesta::mal(&p.id, "db", "no se pudo releer"),
                },
                Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
            }
        }

        //  ── lo que la IA entendió ────────────────────────────────
        //
        //  Un resumen, unas etiquetas y, como mucho, en qué carpeta va. Entra
        //  por aquí ya escrito: aquí no hay modelo ninguno, igual que no hay
        //  red. Lo pide la casa, con el motor del usuario y con su permiso.
        //
        //  Las reglas de qué se pisa son MÁS estrictas que las de `enrich`, y
        //  a propósito: un título que trae una página es un hecho, y esto es
        //  una opinión de un modelo.
        //
        //  NUNCA la nota: esa es tuya y no la escribe nadie más.
        //  El resumen, solo si no había: reescribirlo en cada repaso haría que
        //  lo que leíste ayer diga otra cosa hoy sin que tú hayas tocado nada.
        //  Las etiquetas SE SUMAN, no se reemplazan. `annotate` reemplaza
        //  porque ahí el que escribe eres tú; aquí borrar las tuyas para poner
        //  las suyas sería que la IA te ordena el armario a su gusto.
        //  Y la carpeta, solo si no estaba en ninguna: moverte algo de sitio es
        //  la clase de ayuda que hace que no encuentres tus cosas.
        "classify" => {
            let id = p.params.get("id").and_then(|v| v.as_str()).unwrap_or("");
            let Ok(Some(antes)) = crate::search::una(db, id) else {
                return Respuesta::mal(&p.id, "no_existe", "no hay ninguna con ese id");
            };

            let resumen = p
                .params
                .get("summary")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .trim()
                .chars()
                .take(600)
                .collect::<String>();
            if !resumen.is_empty() && antes.summary.is_empty() {
                let _ = db.execute(
                    "UPDATE captures SET summary = ?2 WHERE id = ?1",
                    rusqlite::params![id, resumen],
                );
            }

            //  Hasta seis suyas, y las tuyas se quedan donde estaban.
            let mut puestas = 0;
            if let Some(ts) = p.params.get("tags").and_then(|v| v.as_array()) {
                for t in ts.iter().filter_map(|x| x.as_str()) {
                    if puestas >= 6 {
                        break;
                    }
                    if crate::ingest::poner_etiqueta(db, id, t).is_ok() {
                        puestas += 1;
                    }
                }
            }

            //  Y la carpeta solo si estaba suelta.
            let mut movida = false;
            if let Some(e) = p.params.get("space").and_then(|v| v.as_str()) {
                let suelta: i64 = db
                    .query_row(
                        "SELECT COUNT(*) FROM capture_spaces WHERE capture_id = ?1",
                        [id],
                        |r| r.get(0),
                    )
                    .unwrap_or(1);
                if suelta == 0 && !e.trim().is_empty() {
                    let _ = crate::ingest::poner_espacio(db, id, e);
                    movida = true;
                }
            }

            //  Y queda apuntado que se miró, salga lo que salga.
            //
            //  Este método se llama TAMBIÉN cuando el modelo no supo decir
            //  nada, y ese es el caso que importa: sin la marca, lo que no se
            //  puede resumir se vuelve a preguntar cada veinte segundos para
            //  siempre. «No se pudo decir nada» es una respuesta.
            let _ = db.execute(
                "UPDATE captures SET summary_at = ?2 WHERE id = ?1",
                rusqlite::params![id, crate::util::ahora_ms()],
            );

            //  Y al índice, que es la mitad de para qué existe esto: un resumen
            //  que no se encuentra buscando no le sirve ni a la IA ni a ti.
            //  Y el vector, que describe lo mismo que el índice: si cambia el
            //  título o el resumen, lo que la captura «quiere decir» cambia con
            //  ellos. Rehacerlo aquí es lo que evita tener dos verdades.
            let _ = crate::search::revectorizar(db, id);

            match crate::db::reindexar(db, id) {
                Ok(()) => match crate::search::una(db, id) {
                    Ok(Some(f)) => Respuesta::bien(
                        &p.id,
                        serde_json::json!({ "item": f, "tagged": puestas, "moved": movida }),
                    ),
                    _ => Respuesta::mal(&p.id, "db", "no se pudo releer"),
                },
                Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
            }
        }

        //  Lo que todavía no ha mirado nadie. Mismo papel que `to_enrich` y con
        //  la misma razón: sin una lista de pendientes, lo que guardaste antes
        //  de encender esto se queda sin resumen para siempre.
        "to_classify" => {
            let n = p
                .params
                .get("limit")
                .and_then(|v| v.as_i64())
                .unwrap_or(8)
                .clamp(1, 40);
            match crate::search::por_clasificar(db, n) {
                Ok(v) => Respuesta::bien(&p.id, serde_json::json!({ "items": v })),
                Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
            }
        }

        //  Solo el parecido, con su número. Es la herramienta de diagnóstico
        //  de todo esto: `search` mezcla lo exacto y lo parecido a propósito, y
        //  cuando algo sale raro hay que poder ver cuál de los dos lo trajo y
        //  con cuánta confianza. Sin esto, calibrar el umbral es adivinar.
        "similar" => {
            let q = p.params.get("query").and_then(|v| v.as_str()).unwrap_or("");
            let n = p
                .params
                .get("limit")
                .and_then(|v| v.as_u64())
                .unwrap_or(10)
                .clamp(1, 100) as usize;
            let minimo = p
                .params
                .get("min")
                .and_then(|v| v.as_f64())
                .map(|x| x as f32)
                .unwrap_or(crate::search::PARECIDO_MINIMO);
            match crate::search::parecidas_desde(db, q, n, minimo) {
                Ok(v) => Respuesta::bien(
                    &p.id,
                    serde_json::json!({
                        "model": crate::vectores::listo(),
                        "items": v.into_iter()
                            .map(|(id, p)| {
                                let titulo = crate::search::una(db, &id).ok().flatten()
                                    .map(|f| f.title).unwrap_or_default();
                                serde_json::json!({ "id": id, "title": titulo, "score": p })
                            })
                            .collect::<Vec<_>>()
                    }),
                ),
                Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
            }
        }

        //  Los vectores del parecido por significado, de N en N.
        //
        //  Aquí no hay red y no hace falta: el modelo está en el disco. Se hace
        //  a trozos para que instalarlo con dos mil capturas dentro no bloquee
        //  la biblioteca cinco minutos, y quien lo llama es el mismo repaso que
        //  ya trae portadas y resúmenes.
        "embed" => {
            let n = p
                .params
                .get("limit")
                .and_then(|v| v.as_i64())
                .unwrap_or(64)
                .clamp(1, 512);
            match crate::search::vectorizar_pendientes(db, n) {
                Ok((hechas, faltan)) => Respuesta::bien(
                    &p.id,
                    serde_json::json!({
                        "done": hechas,
                        "pending": faltan,
                        "model": crate::vectores::listo(),
                    }),
                ),
                Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
            }
        }

        "get" => {
            let id = p.params.get("id").and_then(|v| v.as_str()).unwrap_or("");
            match crate::search::una(db, id) {
                //  With its whole text: a note is copied whole, not its
                //  excerpt.
                Ok(Some(f)) => {
                    let texto: String = db
                        .query_row("SELECT content_text FROM captures WHERE id = ?1", [id], |r| r.get(0))
                        .unwrap_or_default();
                    Respuesta::bien(&p.id, serde_json::json!({ "item": f, "text": texto }))
                }
                Ok(None) => Respuesta::mal(&p.id, "no_existe", "no hay ninguna con ese id"),
                Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
            }
        }

        "stats" => match crate::search::cuentas(db) {
            Ok(c) => Respuesta::bien(&p.id, serde_json::to_value(c).unwrap_or_default()),
            Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
        },

        "integrity_check" => {
            let profundo = p.params.get("deep").and_then(|v| v.as_bool()).unwrap_or(false);
            match crate::mantenimiento::integridad(db, profundo) {
                Ok(i) => Respuesta::bien(&p.id, serde_json::to_value(i).unwrap_or_default()),
                Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
            }
        }

        "repair_index" => match crate::mantenimiento::reparar_indice(db) {
            Ok(n) => Respuesta::bien(&p.id, serde_json::json!({ "reindexed": n })),
            Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
        },

        "backup" => {
            let conservar =
                p.params.get("keep").and_then(|v| v.as_u64()).unwrap_or(5) as usize;
            match crate::mantenimiento::respaldar(db, conservar) {
                Ok(c) => Respuesta::bien(&p.id, serde_json::to_value(c).unwrap_or_default()),
                Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
            }
        }

        "export" => {
            let dir = p.params.get("directory").and_then(|v| v.as_str()).unwrap_or("");
            if dir.is_empty() || !std::path::Path::new(dir).is_absolute() {
                return Respuesta::mal(&p.id, "params", "hace falta una ruta absoluta");
            }
            match crate::mantenimiento::exportar(db, std::path::Path::new(dir)) {
                Ok(x) => Respuesta::bien(&p.id, serde_json::to_value(x).unwrap_or_default()),
                Err(e) => Respuesta::mal(&p.id, "io", e),
            }
        }

        //  Tirar a la basura y sacar de ella. Borrar de verdad es otra cosa y
        //  tiene su propio método: el plan separa exportar de borrar, y por el
        //  mismo motivo separa tirar de destruir.
        "trash" | "untrash" => {
            let id = p.params.get("id").and_then(|v| v.as_str()).unwrap_or("");
            let cuando = if p.method == "trash" {
                Some(crate::util::ahora_ms())
            } else {
                None
            };
            let r = db.execute(
                "UPDATE captures SET trashed_at = ?2 WHERE id = ?1",
                rusqlite::params![id, cuando],
            );
            match r {
                Ok(0) => Respuesta::mal(&p.id, "no_existe", "no hay ninguna con ese id"),
                //  Y el índice detrás: lo tirado deja de encontrarse, lo
                //  recuperado vuelve a encontrarse.
                Ok(_) => match crate::db::reindexar(db, id) {
                    Ok(()) => Respuesta::bien(&p.id, serde_json::json!({ "id": id })),
                    Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
                },
                Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
            }
        }

        //  ── reaparición ─────────────────────────────────────────
        //
        //  El motor decide QUÉ; cuándo y cuántas veces lo decide quien la
        //  enseña, que es quien sabe si estás grabando o si es medianoche.
        //  Aquí se le dan los datos para que pueda decidirlo.
        "revisit" => {
            let espacio = p.params.get("space").and_then(|v| v.as_str());
            let r = (|| -> rusqlite::Result<serde_json::Value> {
                Ok(serde_json::json!({
                    "item": crate::reaparicion::siguiente(db, espacio)?,
                    "shown_today": crate::reaparicion::mostradas_hoy(db)?,
                    "dismissed_in_a_row": crate::reaparicion::descartes_seguidos(db)?,
                    "last_shown_at": crate::reaparicion::ultima_aparicion(db)?,
                }))
            })();
            match r {
                Ok(v) => Respuesta::bien(&p.id, v),
                Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
            }
        }

        //  Se apunta que se enseñó, y luego qué se hizo. Dos métodos y no uno
        //  porque entre los dos pasa el tiempo: enseñar es ahora, y lo que
        //  hagas puede ser dentro de un minuto o nunca.
        "revisit_shown" => {
            let id = p.params.get("id").and_then(|v| v.as_str()).unwrap_or("");
            let razon = p.params.get("reason").and_then(|v| v.as_str()).unwrap_or("");
            match crate::reaparicion::apuntar_mostrada(db, id, razon) {
                Ok(evento) => Respuesta::bien(&p.id, serde_json::json!({ "event": evento })),
                Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
            }
        }
        "revisit_outcome" => {
            let evento = p.params.get("event").and_then(|v| v.as_i64()).unwrap_or(0);
            let cual = p.params.get("outcome").and_then(|v| v.as_str()).unwrap_or("");
            match crate::reaparicion::apuntar_resultado(db, evento, cual) {
                Ok(true) => Respuesta::bien(&p.id, serde_json::json!({ "ok": true })),
                Ok(false) => Respuesta::mal(&p.id, "params",
                    format!("resultado desconocido; los que hay son {:?}",
                            crate::reaparicion::RESULTADOS)),
                Err(e) => Respuesta::mal(&p.id, "db", e.to_string()),
            }
        }

        //  ── traerse lo que ya tenías ────────────────────────────
        //
        //  Tres puertas, todas explícitas: ninguna se ejecuta sola, ninguna
        //  vigila una carpeta y ninguna sale a la red. La ruta la elige el
        //  usuario y la valida el controlador, igual que en `export`.
        "import" => {
            let desde = p.params.get("directory").and_then(|v| v.as_str());
            let fichero = p.params.get("file").and_then(|v| v.as_str());
            let que = p.params.get("kind").and_then(|v| v.as_str()).unwrap_or("");
            let espacio = p.params.get("space").and_then(|v| v.as_str());
            let tope = p.params.get("limit").and_then(|v| v.as_u64()).unwrap_or(5000) as usize;

            fn absoluta(r: Option<&str>) -> Option<&str> {
                r.filter(|x| !x.is_empty() && std::path::Path::new(x).is_absolute())
            }
            let r = match que {
                "folder" => match absoluta(desde) {
                    Some(d) => Ok(crate::importar::carpeta(
                        db,
                        std::path::Path::new(d),
                        tope.clamp(1, 50_000),
                    )),
                    None => Err("hace falta un directorio absoluto"),
                },
                "bookmarks" => match absoluta(fichero) {
                    Some(f) => Ok(crate::importar::marcadores(
                        db,
                        std::path::Path::new(f),
                        espacio,
                    )),
                    None => Err("hace falta un fichero absoluto"),
                },
                "deriva" => match absoluta(desde) {
                    Some(d) => Ok(crate::importar::desde_export(db, std::path::Path::new(d))),
                    None => Err("hace falta un directorio absoluto"),
                },
                _ => Err("no sé importar eso; hay folder, bookmarks y deriva"),
            };
            match r {
                Ok(v) => Respuesta::bien(&p.id, serde_json::to_value(v).unwrap_or_default()),
                Err(e) => Respuesta::mal(&p.id, "params", e),
            }
        }

        //  ── el parte médico ─────────────────────────────────────
        //
        //  Lo que hay que saber cuando algo no va, en una sola respuesta. La
        //  primera pregunta al diagnosticar es siempre «¿qué versión de qué
        //  está hablando con qué?», y contestarla exige mirar cuatro sitios.
        "doctor" => {
            //  Un booleano, no el informe entero: el parte médico se lee de un
            //  vistazo, y para el detalle está `integrity-check`.
            let entera = crate::mantenimiento::integridad(db, false)
                .map(|x| x.ok)
                .unwrap_or(false);
            let c = crate::search::cuentas(db);
            let esquema: i64 = db
                .query_row("PRAGMA user_version", [], |r| r.get(0))
                .unwrap_or(-1);
            let copias = std::fs::read_dir(crate::paths::backups())
                .map(|d| d.filter_map(|e| e.ok()).count())
                .unwrap_or(0);
            Respuesta::bien(
                &p.id,
                serde_json::json!({
                    "version": env!("CARGO_PKG_VERSION"),
                    "schema": esquema,
                    "schema_expected": crate::db::VERSION,
                    "base": crate::paths::base().to_string_lossy(),
                    "socket": crate::paths::socket_description(),
                    "backups": copias,
                    "stats": c.ok(),
                    "integrity": entera,
                }),
            )
        }

        "shutdown" => Respuesta::bien(&p.id, serde_json::json!({ "bye": true })),

        otro => Respuesta::mal(&p.id, "metodo", format!("no sé hacer «{}»", otro)),
    }
}
