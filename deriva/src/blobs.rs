//  El almacén de bytes, direccionado por contenido.
//
//  `blobs/ab/cd/<sha256>`. Que el nombre sea el hash trae tres cosas gratis: el
//  mismo fichero guardado dos veces ocupa una, comprobar la integridad es
//  volver a hashear, y no hay que decidir nombres —ni escapar los que trae el
//  usuario, que es de donde salen la mitad de los agujeros de un almacén de
//  ficheros.
//
//  El orden importa y es el del plan: **primero el blob, después la fila**. Al
//  revés, un corte entre las dos deja una captura visible en la biblioteca
//  apuntando a un fichero que no existe, y eso no se puede arreglar leyendo la
//  base: hay que adivinar qué era. En este orden lo peor que queda es un blob
//  sin dueño, que se ve, se cuenta y se barre.

use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};

//  Lo que no se copia. No es una política de disco: es que copiar un fichero de
//  este tamaño tarda lo bastante como para que la confirmación de Marea deje de
//  ser una confirmación y pase a ser una promesa.
pub const TOPE_FICHERO: u64 = 2 * 1024 * 1024 * 1024;
//  Y lo que puede venir en línea por el protocolo, que es otra cosa: eso viaja
//  en una línea de JSON y hay que tenerlo entero en memoria dos veces.
pub const TOPE_EN_LINEA: usize = 64 * 1024 * 1024;

pub struct Guardado {
    pub hash: String,
    pub bytes: u64,
}

//  Escribe bytes que ya están en memoria.
pub fn guardar_bytes(datos: &[u8]) -> io::Result<Guardado> {
    let hash = crate::util::sha256(datos);
    let destino = crate::paths::blob_de(&hash);
    if destino.exists() {
        //  Ya estaba: dos capturas distintas pueden compartir el mismo
        //  fichero, y el nombre es el hash, así que no hay nada que escribir.
        return Ok(Guardado { hash, bytes: datos.len() as u64 });
    }
    escribir_atomico(&destino, |f| f.write_all(datos))?;
    Ok(Guardado { hash, bytes: datos.len() as u64 })
}

//  Y copia un fichero del disco del usuario. Se hashea leyendo, no cargando: el
//  fichero puede ser un vídeo.
pub fn guardar_fichero(origen: &Path) -> io::Result<Guardado> {
    let meta = std::fs::metadata(origen)?;
    if !meta.is_file() {
        return Err(io::Error::new(io::ErrorKind::InvalidInput, "no es un fichero"));
    }
    if meta.len() > TOPE_FICHERO {
        return Err(io::Error::new(io::ErrorKind::InvalidInput, "demasiado grande"));
    }
    let hash = crate::util::sha256_de_fichero(origen)?;
    let destino = crate::paths::blob_de(&hash);
    if destino.exists() {
        return Ok(Guardado { hash, bytes: meta.len() });
    }
    let mut entrada = std::fs::File::open(origen)?;
    escribir_atomico(&destino, |f| {
        let mut buf = vec![0u8; 1 << 20];
        loop {
            let n = entrada.read(&mut buf)?;
            if n == 0 {
                return Ok(());
            }
            f.write_all(&buf[..n])?;
        }
    })?;
    Ok(Guardado { hash, bytes: meta.len() })
}

//  Entero en un temporal y renombrado encima. Un `rename` dentro del mismo
//  sistema de ficheros es atómico: o está el blob completo o no está, nunca
//  medio blob con el nombre de su hash —que es la única forma de que la
//  comprobación de integridad mienta a favor—.
fn escribir_atomico<F>(destino: &Path, escribir: F) -> io::Result<()>
where
    F: FnOnce(&mut std::fs::File) -> io::Result<()>,
{
    if let Some(p) = destino.parent() {
        std::fs::create_dir_all(p)?;
    }
    std::fs::create_dir_all(crate::paths::tmp())?;
    let mut b = [0u8; 8];
    crate::util::azar(&mut b);
    let temporal = crate::paths::tmp().join(format!("t{}", crate::util::hex(&b)));
    let result = (|| {
        let mut f = std::fs::OpenOptions::new().write(true).create_new(true).open(&temporal)?;
        escribir(&mut f)?;
        //  Al disco antes de renombrar. Sin esto, un corte justo después deja el
        //  nombre puesto sobre un fichero cuyo contenido todavía estaba en la
        //  caché del sistema.
        f.sync_all()?;
        drop(f);
        std::fs::rename(&temporal, destino)
    })();
    // Close the handle before cleanup, including write, sync and rename errors.
    if result.is_err() { let _ = std::fs::remove_file(&temporal); }
    result
}

//  Lo que se quedó a medias de un arranque anterior. Se barre al empezar, que
//  es cuando se sabe que nadie está escribiendo.
pub fn limpiar_temporales() -> io::Result<u64> {
    let d = crate::paths::tmp();
    if !d.exists() {
        return Ok(0);
    }
    let mut n = 0;
    for e in std::fs::read_dir(&d)? {
        let e = e?;
        if e.path().is_file() && std::fs::remove_file(e.path()).is_ok() {
            n += 1;
        }
    }
    Ok(n)
}

//  Todos los blobs que hay en disco. Para contar los que ya no tiene dueño.
pub fn todos() -> io::Result<Vec<(String, PathBuf, u64)>> {
    let mut fuera = Vec::new();
    let raiz = crate::paths::blobs();
    if !raiz.exists() {
        return Ok(fuera);
    }
    for a in std::fs::read_dir(&raiz)? {
        let a = a?;
        if !a.path().is_dir() || a.file_name() == ".tmp" {
            continue;
        }
        for b in std::fs::read_dir(a.path())? {
            let b = b?;
            if !b.path().is_dir() {
                continue;
            }
            for f in std::fs::read_dir(b.path())? {
                let f = f?;
                let meta = match f.metadata() {
                    Ok(m) => m,
                    Err(_) => continue,
                };
                if !meta.is_file() {
                    continue;
                }
                let nombre = f.file_name().to_string_lossy().to_string();
                fuera.push((nombre, f.path(), meta.len()));
            }
        }
    }
    Ok(fuera)
}
