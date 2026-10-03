//  Lo pequeño: identificadores, tiempo, hash y base64.

use sha2::{Digest, Sha256};

pub fn ahora_ms() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}

//  Un identificador con el tiempo delante.
//
//  Podría ser aleatorio entero, pero entonces dos capturas seguidas caen en
//  sitios lejanos del índice y la clave primaria se fragmenta. Con el tiempo
//  delante, lo que se guarda junto se escribe junto, y de paso un id se puede
//  ordenar por edad sin mirar la fila.
pub fn nuevo_id() -> String {
    let mut b = [0u8; 8];
    azar(&mut b);
    format!("{:011x}{}", ahora_ms(), hex(&b))
}

pub fn azar(dest: &mut [u8]) {
    // Time alone collides across concurrent CLI processes, especially on
    // Windows where /dev/urandom does not exist. Fail rather than reuse IDs.
    getrandom::fill(dest).expect("the operating system random source is unavailable");
}

pub fn hex(bytes: &[u8]) -> String {
    let mut s = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        s.push_str(&format!("{:02x}", b));
    }
    s
}

pub fn sha256(bytes: &[u8]) -> String {
    hex(&Sha256::digest(bytes))
}

//  El hash de un fichero sin cargarlo entero en memoria: un vídeo de dos gigas
//  no cabe en la RAM de nadie solo para saber si ya lo tenías.
pub fn sha256_de_fichero(p: &std::path::Path) -> std::io::Result<String> {
    use std::io::Read;
    let mut f = std::fs::File::open(p)?;
    let mut h = Sha256::new();
    let mut buf = vec![0u8; 1 << 20];
    loop {
        let n = f.read(&mut buf)?;
        if n == 0 {
            break;
        }
        h.update(&buf[..n]);
    }
    Ok(hex(&h.finalize()))
}

//  El hash del CONTENIDO, que no es el de los bytes.
//
//  El mismo párrafo copiado dos veces llega con espacios distintos —un salto de
//  línea de más, un tabulador donde había espacios—, y si eso cuenta como texto
//  distinto el duplicado no se detecta nunca. Se normaliza antes: espacios
//  colapsados y extremos limpios.
pub fn hash_de_texto(t: &str) -> String {
    let mut limpio = String::with_capacity(t.len());
    let mut espacio = false;
    for c in t.chars() {
        if c.is_whitespace() {
            espacio = true;
        } else {
            if espacio && !limpio.is_empty() {
                limpio.push(' ');
            }
            espacio = false;
            limpio.push(c);
        }
    }
    sha256(limpio.as_bytes())
}

// ── base64 ───────────────────────────────────────────────────────
//
//  Solo hace falta descodificar, y solo el alfabeto estándar. Traerse una caja
//  entera para treinta líneas en un binario que quiere ser pequeño es pagar de
//  más; hay una prueba de ida y vuelta al lado.

pub fn base64(entrada: &str) -> Option<Vec<u8>> {
    let mut fuera = Vec::with_capacity(entrada.len() / 4 * 3);
    let mut acc: u32 = 0;
    let mut bits: u32 = 0;
    for c in entrada.bytes() {
        //  Los espacios y saltos se ignoran: un base64 de varios megas suele
        //  venir troceado en líneas.
        if c == b'\n' || c == b'\r' || c == b' ' || c == b'\t' {
            continue;
        }
        if c == b'=' {
            break;
        }
        let v = match c {
            b'A'..=b'Z' => c - b'A',
            b'a'..=b'z' => c - b'a' + 26,
            b'0'..=b'9' => c - b'0' + 52,
            b'+' => 62,
            b'/' => 63,
            _ => return None,
        } as u32;
        acc = (acc << 6) | v;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            fuera.push(((acc >> bits) & 0xff) as u8);
        }
    }
    Some(fuera)
}

//  Codificar solo hace falta en las pruebas —el worker recibe base64, no lo
//  produce—, pero la ida sin la vuelta no se puede comprobar.
#[allow(dead_code)]
pub fn a_base64(bytes: &[u8]) -> String {
    const A: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut s = String::with_capacity((bytes.len() + 2) / 3 * 4);
    for trozo in bytes.chunks(3) {
        let b = [
            trozo[0],
            *trozo.get(1).unwrap_or(&0),
            *trozo.get(2).unwrap_or(&0),
        ];
        let n = ((b[0] as u32) << 16) | ((b[1] as u32) << 8) | b[2] as u32;
        s.push(A[(n >> 18) as usize & 63] as char);
        s.push(A[(n >> 12) as usize & 63] as char);
        s.push(if trozo.len() > 1 {
            A[(n >> 6) as usize & 63] as char
        } else {
            '='
        });
        s.push(if trozo.len() > 2 {
            A[n as usize & 63] as char
        } else {
            '='
        });
    }
    s
}

//  De qué sitio es un enlace, dicho con palabras que se pueden buscar: el
//  nombre de la máquina sin `www.` ni `m.` —el tokenizador ya lo parte en
//  «youtube» y «com»—, y los atajos que todo el mundo usa con el nombre de
//  siempre, porque «youtu.be» es YouTube aunque no lo diga. Un fichero, o algo
//  que no es una dirección web, no es de ningún sitio.
pub fn sitio_buscable(direccion: &str) -> String {
    let t = direccion.trim();
    let resto = match t.strip_prefix("https://").or_else(|| t.strip_prefix("http://")) {
        Some(r) => r,
        None => return String::new(),
    };
    let autoridad = resto.split(['/', '?', '#']).next().unwrap_or("");
    let maquina = autoridad.rsplit('@').next().unwrap_or("");
    let maquina = maquina.split(':').next().unwrap_or("").to_lowercase();
    let maquina = maquina
        .strip_prefix("www.")
        .or_else(|| maquina.strip_prefix("m."))
        .unwrap_or(&maquina)
        .to_string();
    if maquina.is_empty() {
        return String::new();
    }
    let tambien = match maquina.as_str() {
        "youtu.be" => " youtube",
        "x.com" | "t.co" => " twitter",
        "redd.it" => " reddit",
        _ => "",
    };
    format!("{}{}", maquina, tambien)
}

// ── la URL, en su forma comparable ───────────────────────────────
//
//  Dos enlaces a la misma página llegan escritos de diez maneras: con `www`,
//  con el `#` de la sección, con la coletilla de campaña que le pega el correo.
//  Si no se normalizan, «esto ya lo tenías» no se cumple nunca y la biblioteca
//  se llena de la misma página seis veces.
//
//  Lo que NO se toca: el orden de los parámetros que quedan, ni las mayúsculas
//  de la ruta. Un identificador de vídeo distingue mayúsculas, y «normalizar»
//  eso convierte dos vídeos en uno.
pub fn canonizar_url(bruta: &str) -> Option<String> {
    let t = bruta.trim();
    let (esquema, resto) = if let Some(r) = t.strip_prefix("https://") {
        ("https", r)
    } else if let Some(r) = t.strip_prefix("http://") {
        ("http", r)
    } else {
        return None;
    };
    //  Fuera el fragmento: `#seccion` es dónde estabas mirando, no qué página.
    let resto = resto.split('#').next().unwrap_or("");
    let (autoridad, camino) = match resto.find('/') {
        Some(i) => (&resto[..i], &resto[i..]),
        None => (resto, "/"),
    };
    if autoridad.is_empty() {
        return None;
    }
    let mut host = autoridad.to_lowercase();
    //  El puerto por defecto sobra: `ejemplo.com:443` y `ejemplo.com` son la
    //  misma máquina.
    for (e, p) in [("https", ":443"), ("http", ":80")] {
        if esquema == e {
            if let Some(h) = host.strip_suffix(p) {
                host = h.to_string();
            }
        }
    }
    if let Some(h) = host.strip_prefix("www.") {
        host = h.to_string();
    }
    let (ruta, consulta) = match camino.find('?') {
        Some(i) => (&camino[..i], &camino[i + 1..]),
        None => (camino, ""),
    };
    let ruta = if ruta.is_empty() { "/" } else { ruta };
    //  Y fuera lo que solo sirve para contar de dónde vienes.
    let mut params: Vec<&str> = Vec::new();
    for p in consulta.split('&') {
        if p.is_empty() {
            continue;
        }
        let clave = p.split('=').next().unwrap_or(p).to_lowercase();
        if clave.starts_with("utm_")
            || matches!(
                clave.as_str(),
                "fbclid" | "gclid" | "gbraid" | "wbraid" | "msclkid" | "mc_eid" | "mc_cid"
                    | "igshid" | "ref_src" | "ref_url" | "s" | "si" | "spm" | "yclid"
            )
        {
            continue;
        }
        params.push(p);
    }
    let mut fuera = format!("{}://{}{}", esquema, host, ruta);
    //  La barra final de una ruta vacía no cuenta, pero la de `/blog/` sí puede
    //  contar en algunos servidores, así que solo se quita la de la raíz.
    if fuera.ends_with("//") {
        fuera.pop();
    }
    if !params.is_empty() {
        fuera.push('?');
        fuera.push_str(&params.join("&"));
    }
    Some(fuera)
}

//  Sin tildes y en minúsculas.
//
//  Para comparar palabras con listas escritas a mano. El índice ya lo hace por
//  su cuenta —`remove_diacritics 2` en el tokenizador—, así que una lista que
//  no lo haga no encaja nunca con lo que sale de él: «tenía» no es «tenia» y la
//  palabra se cuela igual.
pub fn plegar(t: &str) -> String {
    t.to_lowercase()
        .chars()
        .map(|c| match c {
            'á' | 'à' | 'ä' | 'â' => 'a',
            'é' | 'è' | 'ë' | 'ê' => 'e',
            'í' | 'ì' | 'ï' | 'î' => 'i',
            'ó' | 'ò' | 'ö' | 'ô' => 'o',
            'ú' | 'ù' | 'ü' | 'û' => 'u',
            'ñ' => 'n',
            'ç' => 'c',
            otro => otro,
        })
        .collect()
}
