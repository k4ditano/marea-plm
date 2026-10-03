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
