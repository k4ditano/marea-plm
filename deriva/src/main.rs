//  Deriva · el worker de la biblioteca local.
//
//  Un solo binario pequeño. Guarda lo que le sueltas a Marea, lo busca y lo
//  devuelve; nada de esto vive en QML, porque QML se recarga cuando guardas un
//  fichero del repo y una base de datos a medio escribir no sobrevive a eso.
//
//  Dos maneras de hablarle, el mismo despachador detrás: el socket —que es como
//  le habla Marea— y la línea de órdenes, que es como se diagnostica cuando
//  algo va mal sin tener que levantar el escritorio entero.
//
//  Lo que NO hace, y es a propósito: no sale a la red, no abre puertos, no
//  ejecuta nada y no borra nada que no le pidan por su nombre.

mod adaptadores;
mod blobs;
mod db;
mod importar;
mod ingest;
mod mantenimiento;
mod paths;
mod proto;
mod reaparicion;
mod search;
#[cfg(unix)]
mod serve;
mod util;
mod vectores;

#[cfg(test)]
mod pruebas;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let orden = args.first().map(|s| s.as_str()).unwrap_or("");

    let salida = match orden {
        "serve" => {
            #[cfg(unix)]
            if let Err(e) = serve::servir() {
                eprintln!("deriva-worker: {}", e);
                std::process::exit(1);
            }
            #[cfg(not(unix))]
            {
                eprintln!("deriva-worker: Unix socket server is unavailable on Windows; Marea uses the native CLI commands");
                std::process::exit(2);
            }
            #[cfg(unix)]
            return;
        }
        //  The protocol on its input and output: a request per line in, an
        //  answer per line out, the library open and the model for searching
        //  by meaning loaded once. Marea keeps one alive while you search —each
        //  search from the command line loads half a gigabyte again, three
        //  seconds— and lets it go when you stop. It ends with its input.
        "stdio" => {
            use std::io::{BufRead, Write};
            let db = match db::abrir() {
                Ok(d) => d,
                Err(e) => {
                    eprintln!("deriva-worker: {}", e);
                    std::process::exit(1);
                }
            };
            let mut salida = std::io::stdout().lock();
            for linea in std::io::stdin().lock().lines() {
                let Ok(linea) = linea else { break };
                if linea.trim().is_empty() {
                    continue;
                }
                let r = match serde_json::from_str::<proto::Peticion>(&linea) {
                    Ok(p) => proto::despachar(&db, &p),
                    Err(e) => proto::Respuesta::mal("", "json", e.to_string()),
                };
                let _ = writeln!(salida, "{}", serde_json::to_string(&r).unwrap_or_default());
                let _ = salida.flush();
            }
            return;
        }
        "ingest" => por_metodo("ingest", opcion(&args, "--request")),
        "enrich" => {
            if args.iter().any(|a| a == "--request-stdin") {
                // Thumbnails exceed Windows' command-line limit. Keep binary
                // payloads off argv and bound the input before decoding JSON.
                use std::io::Read;
                let mut request = String::new();
                match std::io::stdin().take(1_048_577).read_to_string(&mut request) {
                    Ok(_) if request.len() <= 1_048_576 => por_metodo("enrich", Some(request)),
                    _ => (serde_json::json!({"ok": false, "error": "Invalid or oversized enrichment request"}).to_string(), false),
                }
            } else {
                por_metodo("enrich", opcion(&args, "--request"))
            }
        }
        "search" => {
            let q = opcion(&args, "--query").unwrap_or_default();
            let n = opcion(&args, "--limit").unwrap_or_else(|| "20".into());
            por_metodo(
                "search",
                Some(format!(r#"{{"query":{},"limit":{}}}"#, json_texto(&q), n)),
            )
        }
        "get" => {
            let id = opcion(&args, "--id").unwrap_or_default();
            por_metodo("get", Some(format!(r#"{{"id":{}}}"#, json_texto(&id))))
        }
        "list" => {
            let n = opcion(&args, "--limit").unwrap_or_else(|| "50".into());
            por_metodo("list", Some(format!(r#"{{"limit":{}}}"#, n)))
        }
        //  Any method of the protocol, with its params as they go on the
        //  socket. It is how Marea asks for what has no order of its own
        //  (`trash`, `annotate`, `enrich`, `home` with a filter…) without a
        //  socket of her own. `--preview-file` reads a picture from disk and
        //  hands it to `enrich` as its `preview_b64`: a cover is too big to
        //  travel as an argument.
        "call" => {
            let metodo = args.get(1).cloned().unwrap_or_default();
            let mut params = opcion(&args, "--params").unwrap_or_else(|| "{}".into());
            if let Some(fichero) = opcion(&args, "--preview-file") {
                let bytes = match std::fs::read(&fichero) {
                    Ok(b) => b,
                    Err(e) => {
                        println!("{}", serde_json::json!({ "ok": false, "error": e.to_string() }));
                        std::process::exit(1);
                    }
                };
                let mut v: serde_json::Value =
                    serde_json::from_str(&params).unwrap_or_else(|_| serde_json::json!({}));
                if let Some(o) = v.as_object_mut() {
                    o.insert("preview_b64".into(), serde_json::json!(util::a_base64(&bytes)));
                }
                params = v.to_string();
            }
            por_metodo(&metodo, Some(params))
        }
        "stats" => por_metodo("stats", None),
        "doctor" => por_metodo("doctor", None),
        "import" => {
            //  `--folder <ruta>`, `--bookmarks <fichero>` o `--deriva <carpeta>`.
            let (que, clave, valor) = if let Some(v) = opcion(&args, "--folder") {
                ("folder", "directory", v)
            } else if let Some(v) = opcion(&args, "--bookmarks") {
                ("bookmarks", "file", v)
            } else if let Some(v) = opcion(&args, "--deriva") {
                ("deriva", "directory", v)
            } else {
                eprintln!("deriva-worker: import necesita --folder, --bookmarks o --deriva");
                std::process::exit(2);
            };
            let espacio = opcion(&args, "--space").unwrap_or_default();
            por_metodo(
                "import",
                Some(format!(
                    r#"{{"kind":"{}","{}":{},"space":{}}}"#,
                    que,
                    clave,
                    json_texto(&valor),
                    json_texto(&espacio)
                )),
            )
        }
        //  Todo lo que la página pide al abrirse, de una vez. Por la línea de
        //  órdenes sirve para otra cosa: dejar en un fichero exactamente lo que
        //  ve la interfaz, y que una prueba visual lo reproduzca sin socket.
        "home" => {
            let n = opcion(&args, "--limit").unwrap_or_else(|| "60".into());
            por_metodo("home", Some(format!(r#"{{"limit":{}}}"#, n)))
        }
        "sections" => por_metodo("sections", None),
        //  Qué toca recordar y por qué. Por la línea de órdenes sirve para
        //  auditar el motor: es determinista, así que preguntarlo dos veces
        //  tiene que dar lo mismo, y eso se comprueba mirándolo.
        "revisit" => {
            let e = opcion(&args, "--space").unwrap_or_default();
            por_metodo("revisit", Some(format!(r#"{{"space":{}}}"#, json_texto(&e))))
        }
        "integrity-check" => {
            let profundo = args.iter().any(|a| a == "--deep");
            por_metodo("integrity_check", Some(format!(r#"{{"deep":{}}}"#, profundo)))
        }
        "repair-index" => por_metodo("repair_index", None),
        "backup" => {
            let k = opcion(&args, "--keep").unwrap_or_else(|| "5".into());
            por_metodo("backup", Some(format!(r#"{{"keep":{}}}"#, k)))
        }
        "export" => {
            let d = opcion(&args, "--directory").unwrap_or_default();
            por_metodo("export", Some(format!(r#"{{"directory":{}}}"#, json_texto(&d))))
        }
        "where" => {
            //  Dónde está todo. La primera pregunta cuando algo no aparece.
            println!(
                "{}",
                serde_json::json!({
                    "base": paths::base().to_string_lossy(),
                    "db": paths::db_path().to_string_lossy(),
                    "blobs": paths::blobs().to_string_lossy(),
                    "backups": paths::backups().to_string_lossy(),
                    "socket": paths::socket_description(),
                    "schema": db::VERSION,
                })
            );
            return;
        }
        "" | "-h" | "--help" | "help" => {
            ayuda();
            return;
        }
        otro => {
            eprintln!("deriva-worker: no sé hacer «{}»", otro);
            ayuda();
            std::process::exit(2);
        }
    };

    println!("{}", salida.0);
    if !salida.1 {
        std::process::exit(1);
    }
}

//  Una orden de la línea de órdenes es una petición del protocolo. Un solo
//  camino hacia la base: dos serían dos comportamientos y una prueba que cubre
//  uno de los dos.
fn por_metodo(metodo: &str, params: Option<String>) -> (String, bool) {
    //  `--db` abre OTRA base: sirve para mirar una copia de seguridad antes de
    //  restaurarla, que es la mitad de tener copias. Sin esto, comprobar que
    //  una copia está entera exige sustituir la biblioteca buena por ella.
    let args: Vec<String> = std::env::args().skip(1).collect();
    let abrir = match opcion(&args, "--db") {
        Some(p) => db::abrir_en(std::path::Path::new(&p)),
        None => db::abrir(),
    };
    let db = match abrir {
        Ok(d) => d,
        Err(e) => {
            return (
                serde_json::json!({ "ok": false, "error": e.to_string() }).to_string(),
                false,
            )
        }
    };
    let valor: serde_json::Value = match params {
        Some(s) if !s.trim().is_empty() => match serde_json::from_str(&s) {
            Ok(v) => v,
            Err(e) => {
                return (
                    serde_json::json!({ "ok": false, "error": e.to_string() }).to_string(),
                    false,
                )
            }
        },
        _ => serde_json::Value::Null,
    };
    let p = proto::Peticion {
        v: proto::VERSION,
        id: "cli".into(),
        method: metodo.into(),
        params: valor,
    };
    let r = proto::despachar(&db, &p);
    let ok = r.ok;
    (serde_json::to_string(&r).unwrap_or_default(), ok)
}

fn opcion(args: &[String], nombre: &str) -> Option<String> {
    args.iter()
        .position(|a| a == nombre)
        .and_then(|i| args.get(i + 1))
        .cloned()
}

fn json_texto(s: &str) -> String {
    serde_json::to_string(s).unwrap_or_else(|_| "\"\"".into())
}

fn ayuda() {
    eprintln!(
        r#"deriva-worker · la biblioteca local de Deriva

  serve                              Unix socket server (Unix only)
  ingest   --request <json>          guarda algo
  enrich   --request-stdin           enrich from bounded JSON on stdin
  search   --query <texto> [--limit] busca
  get      --id <id>                 una captura entera
  list     [--limit N]               lo último guardado
  stdio                              the protocol on stdin/stdout, a line each
  call     <method> [--params <json>] [--preview-file <path>]
                                     any method of the protocol
  stats                              cuántas cosas hay
  doctor                             versión, esquema, rutas e integridad
  import   --folder <ruta>           una carpeta de ficheros
           --bookmarks <fichero>     marcadores exportados del navegador
           --deriva <carpeta>        una exportación de Deriva, de vuelta
  home     [--limit N]               lo que ve la página al abrirse
  revisit  [--space <id>]            qué toca recordar, y por qué esa
  integrity-check [--deep]           comprueba que todo sigue ahí
  repair-index                       reconstruye lo que falte del índice
  backup   [--keep N]                copia de seguridad, conservando N
  export   --directory <ruta>        todo lo tuyo, fuera de aquí
  where                              dónde está cada cosa

Con `--db <ruta>` cualquiera de ellas mira OTRA base: así se comprueba una
copia de seguridad sin restaurarla encima de la buena.

Todo sale como una línea de JSON. `MAREA_DERIVA_DIR` mueve la biblioteca
entera, que es como se prueba sin tocar la del usuario."#
    );
}
