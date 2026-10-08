//  Las pruebas del worker.
//
//  Cada una corre sobre una biblioteca recién hecha en un directorio temporal,
//  y hay un cerrojo alrededor porque la ruta viaja en una variable de entorno,
//  que es del proceso entero: sin él, dos pruebas en paralelo se pisarían la
//  biblioteca la una a la otra y fallaría la que llegara segunda.

use super::*;
use std::sync::Mutex;

static CERROJO: Mutex<()> = Mutex::new(());

fn banco<T>(f: impl FnOnce(&rusqlite::Connection) -> T) -> T {
    let _g = CERROJO.lock().unwrap_or_else(|e| e.into_inner());
    let mut b = [0u8; 8];
    util::azar(&mut b);
    let dir = std::env::temp_dir().join(format!("deriva-prueba-{}", util::hex(&b)));
    std::env::set_var("MAREA_DERIVA_DIR", &dir);
    let db = db::abrir().expect("no abre");
    let r = f(&db);
    drop(db);
    let _ = std::fs::remove_dir_all(&dir);
    std::env::remove_var("MAREA_DERIVA_DIR");
    r
}

fn texto(t: &str) -> ingest::Peticion {
    ingest::Peticion { tipo: "text".into(), text: Some(t.into()), ..Default::default() }
}

// ── lo pequeño ───────────────────────────────────────────────────

#[test]
fn base64_ida_y_vuelta() {
    for caso in [
        &b""[..],
        &b"a"[..],
        &b"ab"[..],
        &b"abc"[..],
        &b"\x00\xff\x10marea"[..],
    ] {
        let v = util::base64(&util::a_base64(caso)).expect("descodifica");
        assert_eq!(v, caso, "no vuelve igual");
    }
    //  Y troceado en líneas, que es como llega un base64 grande.
    assert_eq!(util::base64("bWFy\nZWE=").unwrap(), b"marea");
    //  Lo que no es base64 se dice, no se adivina.
    assert!(util::base64("no válido!").is_none());
}

//  Dos enlaces a la misma página llegan escritos de diez maneras. Si esto no
//  los junta, «esto ya lo tenías» no se cumple nunca.
#[test]
fn la_misma_url_escrita_de_varias_maneras_es_una() {
    let esperado = Some("https://ejemplo.com/articulo".to_string());
    for v in [
        "https://ejemplo.com/articulo",
        "https://www.ejemplo.com/articulo",
        "https://EJEMPLO.com/articulo",
        "https://ejemplo.com:443/articulo",
        "https://ejemplo.com/articulo#seccion-3",
        "https://ejemplo.com/articulo?utm_source=boletin&utm_medium=email",
        "  https://ejemplo.com/articulo?fbclid=abc  ",
    ] {
        assert_eq!(util::canonizar_url(v), esperado, "con {}", v);
    }
    //  Pero lo que distingue de verdad se respeta: un identificador de vídeo
    //  distingue mayúsculas, y «normalizar» eso convertiría dos vídeos en uno.
    assert_ne!(
        util::canonizar_url("https://v.com/w?v=aB3"),
        util::canonizar_url("https://v.com/w?v=ab3")
    );
    //  Y lo que no es web no se canoniza: un `file://` no tiene duplicado por
    //  URL, lo tiene por contenido.
    assert_eq!(util::canonizar_url("file:///home/a/x.png"), None);
    assert_eq!(util::canonizar_url("javascript:alert(1)"), None);
}

#[test]
fn el_mismo_texto_con_otros_espacios_es_el_mismo_texto() {
    let a = util::hash_de_texto("Hola   mundo\n\n con espacios ");
    let b = util::hash_de_texto("Hola mundo con espacios");
    assert_eq!(a, b);
    assert_ne!(a, util::hash_de_texto("Hola mundo con espacio"));
}

//  Buscar `it's` no puede fallar. Lo que escribe el usuario no es una consulta
//  FTS5, y pasarla tal cual da un error de sintaxis en vez de resultados.
#[test]
fn lo_que_escribe_el_usuario_nunca_es_sintaxis() {
    for bruta in [
        "it's",
        "\"sin cerrar",
        "* OR 1=1",
        "a AND NOT b",
        "^inicio",
        "-- comentario",
        "(",
    ] {
        let q = search::consulta_fts(bruta);
        if let Some(q) = q {
            //  La prueba de verdad: SQLite la acepta.
            banco(|db| {
                db.query_row(
                    "SELECT COUNT(*) FROM captures_fts WHERE captures_fts MATCH ?1",
                    [&q],
                    |r| r.get::<_, i64>(0),
                )
                .unwrap_or_else(|e| panic!("«{}» → «{}» no compila: {}", bruta, q, e));
            });
        }
    }
    //  Una consulta vacía no busca nada, en vez de buscarlo todo.
    assert_eq!(search::consulta_fts("   "), None);
    assert_eq!(search::consulta_fts("!!!"), None);
}

// ── guardar ──────────────────────────────────────────────────────

#[test]
fn guardar_un_texto_y_encontrarlo() {
    banco(|db| {
        let mut p = texto("La marea sube dos veces al día y baja otras dos.");
        p.title = Some("Mareas".into());
        p.tags = vec!["mar".into()];
        let r = ingest::ingerir(db, &p);
        assert_eq!(r.len(), 1);
        assert_eq!(r[0].status, "saved");

        assert_eq!(search::buscar(db, "marea", 10).unwrap().len(), 1);
        //  Por el título, por el cuerpo y por la etiqueta.
        assert_eq!(search::buscar(db, "Mareas", 10).unwrap().len(), 1);
        assert_eq!(search::buscar(db, "mar", 10).unwrap().len(), 1);
        //  Y con un fragmento marcado, que es lo que enseña la lista.
        assert!(search::buscar(db, "marea", 10).unwrap()[0].snippet.is_some());
    });
}

#[test]
fn lo_mismo_dos_veces_es_un_duplicado() {
    banco(|db| {
        let p = texto("Exactamente lo mismo.");
        let a = ingest::ingerir(db, &p);
        assert_eq!(a[0].status, "saved");
        //  Con otros espacios: sigue siendo lo mismo.
        let b = ingest::ingerir(db, &texto("Exactamente    lo\n mismo. "));
        assert_eq!(b[0].status, "duplicate");
        assert_eq!(b[0].duplicate_of, a[0].id);
        assert_eq!(search::cuentas(db).unwrap().captures, 1);
    });
}

#[test]
fn la_misma_pagina_con_otra_coletilla_es_un_duplicado() {
    banco(|db| {
        let una = ingest::Peticion {
            tipo: "url".into(),
            source_url: Some("https://ejemplo.com/post".into()),
            ..Default::default()
        };
        assert_eq!(ingest::ingerir(db, &una)[0].status, "saved");
        let otra = ingest::Peticion {
            tipo: "url".into(),
            source_url: Some("https://www.ejemplo.com/post?utm_source=x".into()),
            ..Default::default()
        };
        assert_eq!(ingest::ingerir(db, &otra)[0].status, "duplicate");
    });
}

//  Volver a guardar algo que tiraste tiene que funcionar. Si no, el borrado
//  sería una condena: nunca más podrías guardar esa página.
#[test]
fn lo_tirado_no_cuenta_como_duplicado() {
    banco(|db| {
        let a = ingest::ingerir(db, &texto("Una cosa."));
        let id = a[0].id.clone().unwrap();
        db.execute("UPDATE captures SET trashed_at = 1 WHERE id = ?1", [&id])
            .unwrap();
        db::reindexar(db, &id).unwrap();
        assert_eq!(ingest::ingerir(db, &texto("Una cosa."))[0].status, "saved");
        //  Y lo tirado deja de encontrarse.
        assert_eq!(search::buscar(db, "Una cosa", 10).unwrap().len(), 1);
    });
}

#[test]
fn un_tipo_que_no_existe_se_rechaza() {
    banco(|db| {
        let p = ingest::Peticion { tipo: "cualquiera".into(), ..Default::default() };
        let r = ingest::ingerir(db, &p);
        assert_eq!(r[0].status, "rejected");
        assert_eq!(r[0].reason.as_deref(), Some("tipo_desconocido"));
    });
}

#[test]
fn sin_contenido_no_se_guarda_una_captura_vacia() {
    banco(|db| {
        let r = ingest::ingerir(db, &ingest::Peticion { tipo: "text".into(), ..Default::default() });
        assert_eq!(r[0].status, "rejected");
        assert_eq!(r[0].reason.as_deref(), Some("sin_contenido"));
    });
}

// ── los ficheros ─────────────────────────────────────────────────

#[test]
fn un_fichero_se_copia_una_sola_vez_aunque_se_guarde_dos() {
    banco(|db| {
        let f = std::env::temp_dir().join(format!("deriva-f-{}.txt", util::ahora_ms()));
        std::fs::write(&f, b"unos bytes cualesquiera").unwrap();

        let p = ingest::Peticion {
            tipo: "document".into(),
            paths: vec![f.to_string_lossy().to_string()],
            ..Default::default()
        };
        let a = ingest::ingerir(db, &p);
        assert_eq!(a[0].status, "saved");

        //  El blob está donde dice el plan y su nombre es su hash.
        let hash = util::sha256(b"unos bytes cualesquiera");
        let sitio = paths::blob_de(&hash);
        assert!(sitio.exists(), "no está en {}", sitio.display());
        assert_eq!(std::fs::read(&sitio).unwrap(), b"unos bytes cualesquiera");

        //  El mismo fichero otra vez: duplicado, y ni una copia más.
        assert_eq!(ingest::ingerir(db, &p)[0].status, "duplicate");
        assert_eq!(blobs::todos().unwrap().len(), 1);

        let _ = std::fs::remove_file(&f);
    });
}

#[test]
fn un_lote_da_un_resultado_por_fichero() {
    banco(|db| {
        let mut rutas = Vec::new();
        for i in 0..3 {
            let f = std::env::temp_dir().join(format!("deriva-l-{}-{}.txt", util::ahora_ms(), i));
            std::fs::write(&f, format!("fichero {}", i)).unwrap();
            rutas.push(f.to_string_lossy().to_string());
        }
        //  Y uno repetido: de cuatro arrastrados, tres nuevos y uno que ya
        //  estaba no es un fallo del lote.
        rutas.push(rutas[0].clone());
        let p = ingest::Peticion { tipo: "file".into(), paths: rutas.clone(), ..Default::default() };
        let r = ingest::ingerir(db, &p);
        assert_eq!(r.len(), 4);
        assert_eq!(r.iter().filter(|x| x.status == "saved").count(), 3);
        assert_eq!(r.iter().filter(|x| x.status == "duplicate").count(), 1);
        for ruta in rutas.iter().take(3) {
            let _ = std::fs::remove_file(ruta);
        }
    });
}

//  Los enlaces se resuelven antes de copiar. Sin eso, un enlace con nombre de
//  foto apuntando a `/etc/passwd` se copiaría a la biblioteca tan tranquilo.
#[test]
fn lo_que_no_se_deja_copiar() {
    banco(|db| {
        let missing = paths::base().join("not present.txt").to_string_lossy().into_owned();
        let directory = std::env::temp_dir().to_string_lossy().into_owned();
        let casos = [
            ("relativa.txt", "ruta_relativa"),
            (missing.as_str(), "no_existe"),
            #[cfg(unix)]
            ("/proc/self/status", "ruta_del_sistema"),
            (directory.as_str(), "no_es_un_fichero"),
        ];
        for (ruta, motivo) in casos {
            let p = ingest::Peticion {
                tipo: "file".into(),
                paths: vec![ruta.into()],
                ..Default::default()
            };
            let r = ingest::ingerir(db, &p);
            assert_eq!(r[0].status, "rejected", "con {}", ruta);
            assert_eq!(r[0].reason.as_deref(), Some(motivo), "con {}", ruta);
        }
        //  Y la biblioteca no se copia a sí misma.
        let dentro = paths::base().join("library.sqlite3");
        let p = ingest::Peticion {
            tipo: "file".into(),
            paths: vec![dentro.to_string_lossy().to_string()],
            ..Default::default()
        };
        assert_eq!(
            ingest::ingerir(db, &p)[0].reason.as_deref(),
            Some("ya_es_de_la_biblioteca")
        );
    });
}

#[test]
fn una_imagen_en_linea_se_guarda_por_sus_bytes() {
    banco(|db| {
        let datos = b"\x89PNG\r\n\x1a\nfingido";
        let p = ingest::Peticion {
            tipo: "image".into(),
            source_url: Some("https://ejemplo.com/pagina".into()),
            inline: Some(ingest::EnLinea {
                mime: Some("image/png".into()),
                name: Some("foto.png".into()),
                base64: util::a_base64(datos),
            }),
            ..Default::default()
        };
        let r = ingest::ingerir(db, &p);
        assert_eq!(r[0].status, "saved");
        let f = search::una(db, r[0].id.as_ref().unwrap()).unwrap().unwrap();
        assert_eq!(f.blob_hash.as_deref(), Some(util::sha256(datos).as_str()));
        assert_eq!(f.blob_bytes, Some(datos.len() as i64));
        assert_eq!(f.blob_mime.as_deref(), Some("image/png"));
    });
}

#[test]
fn un_base64_roto_se_rechaza_en_vez_de_guardar_basura() {
    banco(|db| {
        let p = ingest::Peticion {
            tipo: "image".into(),
            inline: Some(ingest::EnLinea {
                mime: None,
                name: None,
                base64: "esto no es base64 ###".into(),
            }),
            ..Default::default()
        };
        assert_eq!(ingest::ingerir(db, &p)[0].reason.as_deref(), Some("base64_invalido"));
    });
}

// ── el índice ────────────────────────────────────────────────────

//  El índice no se mantiene con disparadores, y esta es la prueba de que la
//  decisión está bien atendida: las etiquetas viven en otra tabla y un
//  disparador sobre `captures` no las vería.
#[test]
fn cambiar_una_etiqueta_se_busca() {
    banco(|db| {
        let r = ingest::ingerir(db, &texto("Un texto sin nada especial."));
        let id = r[0].id.clone().unwrap();
        assert_eq!(search::buscar(db, "bicicleta", 10).unwrap().len(), 0);

        ingest::poner_etiqueta(db, &id, "Bicicleta").unwrap();
        db::reindexar(db, &id).unwrap();
        assert_eq!(search::buscar(db, "bicicleta", 10).unwrap().len(), 1);
    });
}

#[test]
fn tirar_y_recuperar_saca_y_devuelve_del_indice() {
    banco(|db| {
        let r = ingest::ingerir(db, &texto("Algo que se busca por su palabra rara: xilofono."));
        let id = r[0].id.clone().unwrap();
        assert_eq!(search::buscar(db, "xilofono", 10).unwrap().len(), 1);

        let p = proto::Peticion {
            v: 1,
            id: "t".into(),
            method: "trash".into(),
            params: serde_json::json!({ "id": id }),
        };
        assert!(proto::despachar(db, &p).ok);
        assert_eq!(search::buscar(db, "xilofono", 10).unwrap().len(), 0);
        //  Pero sigue estando: tirar no es destruir.
        assert!(search::una(db, &id).unwrap().is_some());

        let p = proto::Peticion { method: "untrash".into(), ..p };
        assert!(proto::despachar(db, &p).ok);
        assert_eq!(search::buscar(db, "xilofono", 10).unwrap().len(), 1);
    });
}

//  El título pesa más que el cuerpo. Sin pesos, una palabra perdida en un
//  artículo de diez mil compite con la misma palabra en el título.
#[test]
fn el_titulo_manda_sobre_el_cuerpo() {
    banco(|db| {
        let mut cuerpo = texto(&format!("{} ballena {}", "relleno ".repeat(200), "relleno ".repeat(200)));
        cuerpo.title = Some("Un artículo largo".into());
        ingest::ingerir(db, &cuerpo);

        let mut titulo = texto("Nada que ver aquí dentro.");
        titulo.title = Some("Ballena".into());
        ingest::ingerir(db, &titulo);

        let r = search::buscar(db, "ballena", 10).unwrap();
        assert_eq!(r.len(), 2);
        assert_eq!(r[0].title, "Ballena", "el título tendría que ir primero");
    });
}

// ── integridad, copia y exportación ──────────────────────────────

#[test]
fn una_biblioteca_recien_hecha_esta_entera() {
    banco(|db| {
        ingest::ingerir(db, &texto("algo"));
        let i = mantenimiento::integridad(db, true).unwrap();
        assert!(i.ok, "{:?}", i);
        assert_eq!(i.sqlite, "ok");
        assert!(i.missing_blobs.is_empty());
        assert_eq!(i.orphan_blobs, 0);
    });
}

//  El fallo que de verdad importa: la biblioteca enseña algo que ya no se puede
//  abrir. Tiene que decirlo por su nombre, no fallar al abrirlo.
#[test]
fn un_blob_que_desaparece_se_denuncia() {
    banco(|db| {
        let f = std::env::temp_dir().join(format!("deriva-i-{}.bin", util::ahora_ms()));
        std::fs::write(&f, b"contenido").unwrap();
        let p = ingest::Peticion {
            tipo: "file".into(),
            paths: vec![f.to_string_lossy().to_string()],
            ..Default::default()
        };
        ingest::ingerir(db, &p);
        let _ = std::fs::remove_file(&f);

        let hash = util::sha256(b"contenido");
        std::fs::remove_file(paths::blob_de(&hash)).unwrap();

        let i = mantenimiento::integridad(db, false).unwrap();
        assert!(!i.ok);
        assert_eq!(i.missing_blobs, vec![hash]);
    });
}

#[test]
fn un_blob_corrupto_solo_sale_en_la_revision_profunda() {
    banco(|db| {
        let f = std::env::temp_dir().join(format!("deriva-c-{}.bin", util::ahora_ms()));
        std::fs::write(&f, b"original").unwrap();
        let p = ingest::Peticion {
            tipo: "file".into(),
            paths: vec![f.to_string_lossy().to_string()],
            ..Default::default()
        };
        ingest::ingerir(db, &p);
        let _ = std::fs::remove_file(&f);

        //  Alguien escribe dentro del blob. El nombre sigue siendo el hash de
        //  antes, así que solo se ve volviendo a hashear.
        std::fs::write(paths::blob_de(&util::sha256(b"original")), b"otra cosa").unwrap();

        assert!(mantenimiento::integridad(db, false).unwrap().ok);
        let profunda = mantenimiento::integridad(db, true).unwrap();
        assert!(!profunda.ok);
        assert_eq!(profunda.corrupt_blobs.len(), 1);
    });
}

#[test]
fn un_indice_incompleto_se_repara() {
    banco(|db| {
        let r = ingest::ingerir(db, &texto("palabra rarisima: zurriburri"));
        let id = r[0].id.clone().unwrap();
        db.execute("DELETE FROM captures_fts WHERE capture_id = ?1", [&id])
            .unwrap();
        assert_eq!(search::buscar(db, "zurriburri", 10).unwrap().len(), 0);
        assert!(!mantenimiento::integridad(db, false).unwrap().ok);

        assert_eq!(mantenimiento::reparar_indice(db).unwrap(), 1);
        assert_eq!(search::buscar(db, "zurriburri", 10).unwrap().len(), 1);
        assert!(mantenimiento::integridad(db, false).unwrap().ok);
    });
}

#[test]
fn la_copia_de_seguridad_se_puede_abrir_y_tiene_lo_mismo() {
    banco(|db| {
        for i in 0..3 {
            ingest::ingerir(db, &texto(&format!("cosa numero {}", i)));
        }
        let c = mantenimiento::respaldar(db, 5).unwrap();
        assert!(c.bytes > 0);

        let copia = db::abrir_en(std::path::Path::new(&c.path)).unwrap();
        assert_eq!(search::cuentas(&copia).unwrap().captures, 3);
        //  Y se puede buscar en ella: el índice viaja con la base.
        assert_eq!(search::buscar(&copia, "numero", 10).unwrap().len(), 3);
    });
}

#[test]
fn las_copias_viejas_se_tiran() {
    banco(|db| {
        ingest::ingerir(db, &texto("una"));
        for _ in 0..4 {
            mantenimiento::respaldar(db, 2).unwrap();
            //  Los nombres llevan milisegundos; sin esperar, dos copias del
            //  mismo milisegundo serían el mismo fichero.
            std::thread::sleep(std::time::Duration::from_millis(2));
        }
        let cuantas = std::fs::read_dir(paths::backups()).unwrap().count();
        assert_eq!(cuantas, 2);
    });
}

//  Irse tiene que ser posible, y con los ficheros usables: un adjunto llamado
//  `9f2a…` es tuyo igual, pero no lo puedes abrir.
#[test]
fn exportar_deja_todo_legible_sin_este_programa() {
    banco(|db| {
        let f = std::env::temp_dir().join(format!("deriva-e-{}.txt", util::ahora_ms()));
        std::fs::write(&f, b"el adjunto").unwrap();
        let mut p = ingest::Peticion {
            tipo: "document".into(),
            paths: vec![f.to_string_lossy().to_string()],
            ..Default::default()
        };
        p.tags = vec!["viaje".into()];
        ingest::ingerir(db, &p);
        ingest::ingerir(db, &texto("una nota suelta"));
        let _ = std::fs::remove_file(&f);

        let destino = paths::base().join("salida");
        let x = mantenimiento::exportar(db, &destino).unwrap();
        assert_eq!(x.captures, 2);
        assert_eq!(x.files, 1);

        let jsonl = std::fs::read_to_string(destino.join("captures.jsonl")).unwrap();
        assert_eq!(jsonl.lines().count(), 2);
        assert!(jsonl.contains("una nota suelta"), "falta el texto entero");
        assert!(jsonl.contains("viaje"), "faltan las etiquetas");
        assert!(destino.join("manifest.json").exists());

        //  El adjunto, con nombre de persona y su contenido intacto.
        let ficheros: Vec<_> = std::fs::read_dir(destino.join("files"))
            .unwrap()
            .filter_map(|e| e.ok())
            .collect();
        assert_eq!(ficheros.len(), 1);
        let nombre = ficheros[0].file_name().to_string_lossy().to_string();
        assert!(nombre.ends_with(".txt"), "se llama «{}»", nombre);
        assert_eq!(std::fs::read(ficheros[0].path()).unwrap(), b"el adjunto");
    });
}

// ── lo que necesita la página ────────────────────────────────────

//  La navegación sale de la base, no de una lista escrita en QML: los espacios
//  los crea el usuario, y una barra lateral fija dejaría de contar el día que
//  cree el cuarto.
#[test]
fn la_navegacion_cuenta_lo_que_hay() {
    banco(|db| {
        let mut p = texto("una cosa");
        p.space = Some("Proyectos".into());
        p.tags = vec!["azul".into()];
        ingest::ingerir(db, &p);
        ingest::ingerir(db, &texto("otra cosa suelta"));

        let s = search::secciones(db).unwrap();
        let de = |id: &str| s.iter().find(|x| x.id == id).map(|x| x.count).unwrap_or(-1);
        assert_eq!(de("inbox"), 2);
        assert_eq!(de("today"), 2);
        //  Los tres del plan están sembrados, y solo cuenta el que tiene algo.
        assert_eq!(de("proyectos"), 1);
        assert_eq!(de("leer-luego"), 0);
        assert_eq!(de("inspiracion"), 0);
        assert_eq!(de("tags"), 1);
        //  Y en el orden que enseña la lámina: entrada, hoy, espacios, etiquetas.
        assert_eq!(s[0].id, "inbox");
        assert_eq!(s[1].id, "today");
        assert_eq!(s[s.len() - 1].id, "tags");
    });
}

#[test]
fn se_puede_listar_por_espacio_y_por_etiqueta() {
    banco(|db| {
        let mut a = texto("del proyecto");
        a.space = Some("Proyectos".into());
        a.tags = vec!["azul".into()];
        ingest::ingerir(db, &a);
        let mut b = texto("de inspiración");
        b.space = Some("Inspiración".into());
        ingest::ingerir(db, &b);

        let todo = search::Filtro::default();
        assert_eq!(search::listar(db, 50, None, &todo).unwrap().len(), 2);

        let solo = search::Filtro { space: Some("proyectos".into()), ..Default::default() };
        let r = search::listar(db, 50, None, &solo).unwrap();
        assert_eq!(r.len(), 1);
        assert_eq!(r[0].title, "del proyecto");

        let etiq = search::Filtro { tag: Some("azul".into()), ..Default::default() };
        assert_eq!(search::listar(db, 50, None, &etiq).unwrap().len(), 1);

        //  Un espacio que no existe no devuelve todo: devuelve nada. Un filtro
        //  que se ignora en silencio es peor que un filtro que no existe.
        let nada = search::Filtro { space: Some("marte".into()), ..Default::default() };
        assert_eq!(search::listar(db, 50, None, &nada).unwrap().len(), 0);
    });
}

//  «Han vuelto a la superficie» significa eso y no «lo último guardado».
//  Rellenar esa banda con lo reciente sería mentir con el título puesto.
#[test]
fn solo_vuelve_a_la_superficie_lo_que_ya_tocaba() {
    banco(|db| {
        for i in 0..4 {
            ingest::ingerir(db, &texto(&format!("cosa {}", i)));
        }
        assert_eq!(search::reaparecidas(db, 5).unwrap().len(), 0, "no había nada aplazado");

        let ids: Vec<String> = search::listar(db, 5, None, &search::Filtro::default())
            .unwrap()
            .iter()
            .map(|f| f.id.clone())
            .collect();
        //  Una para ayer y otra para dentro de una semana.
        let ahora = util::ahora_ms();
        db.execute("UPDATE captures SET snoozed_until = ?2 WHERE id = ?1",
                   rusqlite::params![ids[0], ahora - 86_400_000]).unwrap();
        db.execute("UPDATE captures SET snoozed_until = ?2 WHERE id = ?1",
                   rusqlite::params![ids[1], ahora + 604_800_000]).unwrap();

        let v = search::reaparecidas(db, 5).unwrap();
        assert_eq!(v.len(), 1, "la de la semana que viene todavía no toca");
        assert_eq!(v[0].id, ids[0]);
    });
}

//  El inspector es lo único que escribe, y solo escribe lo que es tuyo: la
//  nota, las etiquetas y el favorito. El contenido no se edita.
#[test]
fn la_nota_y_las_etiquetas_se_pueden_cambiar_y_se_buscan() {
    banco(|db| {
        let r = ingest::ingerir(db, &texto("un texto cualquiera"));
        let id = r[0].id.clone().unwrap();

        let p = proto::Peticion {
            v: 1,
            id: "a".into(),
            method: "annotate".into(),
            params: serde_json::json!({
                "id": id, "note": "lo guardé por el tercer párrafo",
                "tags": ["relectura", "AZUL"], "favorite": true,
            }),
        };
        let resp = proto::despachar(db, &p);
        assert!(resp.ok, "{:?}", resp.error);

        let f = search::una(db, &id).unwrap().unwrap();
        assert_eq!(f.note, "lo guardé por el tercer párrafo");
        assert!(f.favorite);
        //  Normalizadas: dos etiquetas con el mismo nombre son la misma.
        assert_eq!(f.tags, vec!["azul".to_string(), "relectura".to_string()]);

        //  Y se busca por la nota y por la etiqueta, que es la prueba de que el
        //  índice se rehízo.
        assert_eq!(search::buscar(db, "tercer", 10).unwrap().len(), 1);
        assert_eq!(search::buscar(db, "relectura", 10).unwrap().len(), 1);

        //  El contenido, en cambio, no tiene por dónde tocarse: no hay método.
        let malo = proto::Peticion { method: "edit_content".into(), ..p };
        assert!(!proto::despachar(db, &malo).ok);
    });
}

//  Una biblioteca de ayer se abre hoy.
//
//  Es el fallo que casi se cuela: la columna `source` se añadió al esquema
//  editándolo, y eso solo sirve para bases nuevas. La de alguien que lleva
//  usando esto desde la semana pasada dice `user_version = 1`, no tiene la
//  columna, y todo lo que lee una captura pregunta por ella.
//
//  Así que la prueba no es «migra bien», es «después de migrar, la biblioteca
//  de ayer se puede leer entera y lo de dentro sigue estando».
#[test]
fn una_biblioteca_de_la_version_anterior_se_migra() {
    let _g = CERROJO.lock().unwrap_or_else(|e| e.into_inner());
    let mut b = [0u8; 8];
    util::azar(&mut b);
    let dir = std::env::temp_dir().join(format!("deriva-vieja-{}", util::hex(&b)));
    std::env::set_var("MAREA_DERIVA_DIR", &dir);

    //  Una v1 de verdad: el esquema de entonces, que es el de ahora sin la
    //  columna de la fuente y con la ruta de la miniatura en vez de su hash.
    {
        let vieja = db::abrir().expect("no abre");
        //  Primero lo de dentro y después dejarla como era: al revés, el
        //  INSERT de hoy —que ya nombra la columna— falla y la prueba se queda
        //  sin el dato que tiene que sobrevivir.
        ingest::ingerir(&vieja, &texto("lo de ayer"));
        vieja
            .execute_batch(
                "ALTER TABLE captures DROP COLUMN source;
                 ALTER TABLE captures DROP COLUMN summary;
                 ALTER TABLE captures DROP COLUMN summary_at;
                 ALTER TABLE captures DROP COLUMN preview_hash;
                 ALTER TABLE captures ADD COLUMN preview_path TEXT;
                 DROP TABLE capture_vectors;
                 DROP TABLE captures_fts;
                 CREATE VIRTUAL TABLE captures_fts USING fts5(
                     capture_id UNINDEXED,
                     title, author, excerpt, note, content_text, tags,
                     tokenize = \"unicode61 remove_diacritics 2\"
                 );
                 PRAGMA user_version = 1;",
            )
            .expect("no la puedo dejar como estaba");
    }

    //  Y al abrirla otra vez, con el worker de hoy.
    let db = db::abrir().expect("no abre la vieja");
    let v: i64 = db
        .query_row("PRAGMA user_version", [], |r| r.get(0))
        .unwrap();
    assert_eq!(v, db::VERSION);
    let filas = search::listar(&db, 10, None, &search::Filtro::default()).expect("no lista");
    assert_eq!(filas.len(), 1, "lo de ayer tiene que seguir estando");
    assert_eq!(filas[0].source, "", "lo viejo no viene de ningún sitio y se dice así");
    //  Y el índice se ha rehecho: lo de ayer se sigue encontrando, que es lo
    //  que se pierde si se tira la tabla FTS y no se vuelve a llenar.
    assert_eq!(search::buscar(&db, "ayer", 10).unwrap().len(), 1,
               "el índice no se rehizo tras cambiarle las columnas");
    //  Y hay copia: migrar sin copia es lo que el plan prohíbe.
    let copias = std::fs::read_dir(paths::backups())
        .map(|d| d.count())
        .unwrap_or(0);
    assert!(copias > 0, "no se guardó copia antes de migrar");

    drop(db);
    let _ = std::fs::remove_dir_all(&dir);
    std::env::remove_var("MAREA_DERIVA_DIR");
}

// ── de qué sitio viene ───────────────────────────────────────────
//
//  Un enlace de YouTube y un enlace a un PDF no son lo mismo aunque los dos
//  sean `text/uri-list`. Todo esto se saca de la URL, sin salir a la red.

fn url(u: &str) -> ingest::Peticion {
    ingest::Peticion { tipo: "url".into(), source_url: Some(u.into()), ..Default::default() }
}

//  Un vídeo es un vídeo aunque la URL no acabe en `.mp4`.
#[test]
fn un_enlace_de_youtube_es_un_video() {
    banco(|db| {
        let r = ingest::ingerir(db, &url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"));
        let f = search::una(db, r[0].id.as_ref().unwrap()).unwrap().unwrap();
        assert_eq!(f.tipo, "video");
        assert_eq!(f.source, "youtube");
    });
}

//  Y las cinco maneras de escribir el mismo vídeo son el mismo vídeo. Sin esto,
//  arrastrarlo desde el móvil y desde el escritorio guarda dos capturas.
#[test]
fn el_mismo_video_escrito_de_cinco_maneras_es_uno() {
    banco(|db| {
        let iguales = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=90s",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        ];
        assert_eq!(ingest::ingerir(db, &url(iguales[0]))[0].status, "saved");
        for u in &iguales[1..] {
            assert_eq!(ingest::ingerir(db, &url(u))[0].status, "duplicate", "con {}", u);
        }
        assert_eq!(search::cuentas(db).unwrap().captures, 1);
    });
}

//  Un canal no es un vídeo: sin comprobar la forma del identificador, se
//  guardaría una miniatura que no existe.
#[test]
fn un_canal_de_youtube_no_finge_ser_un_video() {
    banco(|db| {
        let r = ingest::ingerir(db, &url("https://www.youtube.com/@alguien"));
        let f = search::una(db, r[0].id.as_ref().unwrap()).unwrap().unwrap();
        assert_eq!(f.source, "youtube");
        //  Sigue siendo de YouTube, pero sin identificador no hay canónica que
        //  inventarse.
        assert_eq!(f.canonical_url.as_deref(), Some("https://youtube.com/@alguien"));
    });
}

#[test]
fn reddit_x_y_github_se_reconocen_y_se_recortan() {
    banco(|db| {
        //  El slug del final cambia y ensuciaría el duplicado.
        let a = ingest::ingerir(db,
            &url("https://www.reddit.com/r/rust/comments/abc123/un_titulo_largo/"));
        let f = search::una(db, a[0].id.as_ref().unwrap()).unwrap().unwrap();
        assert_eq!(f.source, "reddit");
        assert_eq!(f.canonical_url.as_deref(),
                   Some("https://reddit.com/r/rust/comments/abc123"));
        //  Y el slug sirve de título, que es mejor que la dirección entera.
        assert_eq!(f.title, "Un titulo largo");
        //  Otro slug, mismo hilo: duplicado.
        assert_eq!(ingest::ingerir(db,
            &url("https://old.reddit.com/r/rust/comments/abc123/otro_slug/"))[0].status,
            "duplicate");

        let b = ingest::ingerir(db, &url("https://twitter.com/alguien/status/123456"));
        let f = search::una(db, b[0].id.as_ref().unwrap()).unwrap().unwrap();
        assert_eq!(f.source, "x");
        assert_eq!(f.canonical_url.as_deref(), Some("https://x.com/alguien/status/123456"));
        assert_eq!(f.title, "@alguien");

        let c = ingest::ingerir(db, &url("https://github.com/rust-lang/rust/issues/9"));
        let f = search::una(db, c[0].id.as_ref().unwrap()).unwrap().unwrap();
        assert_eq!(f.source, "github");
        assert_eq!(f.tipo, "code");
        assert_eq!(f.title, "rust-lang/rust");
    });
}

//  Un enlace directo a un PDF es un documento, no «una web».
#[test]
fn la_extension_de_la_url_tambien_dice_que_es() {
    banco(|db| {
        let r = ingest::ingerir(db, &url("https://ejemplo.com/papers/informe-2026.pdf"));
        let f = search::una(db, r[0].id.as_ref().unwrap()).unwrap().unwrap();
        assert_eq!(f.tipo, "document");
        assert_eq!(f.source, "pdf");
        assert_eq!(f.title, "informe-2026.pdf");
    });
}

//  Y una página cualquiera se queda con su dominio de título, que dice más que
//  «Sin título» y muchísimo menos que una dirección de doscientos caracteres.
#[test]
fn una_pagina_cualquiera_se_titula_con_su_dominio() {
    banco(|db| {
        let r = ingest::ingerir(db, &url("https://ejemplo.com/una/ruta/larga?a=1&b=2"));
        let f = search::una(db, r[0].id.as_ref().unwrap()).unwrap().unwrap();
        assert_eq!(f.tipo, "url");
        assert_eq!(f.source, "web");
        assert_eq!(f.title, "ejemplo.com");
    });
}

//  Lo que quien ingiere ya sabe manda sobre el adaptador: si dijo «documento»,
//  sabe más que nosotros. El adaptador solo pisa el genérico «url».
#[test]
fn el_adaptador_no_pisa_lo_que_ya_se_sabia() {
    banco(|db| {
        let mut p = url("https://www.youtube.com/watch?v=dQw4w9WgXcQ");
        p.tipo = "document".into();
        p.title = Some("Lo llamo yo".into());
        let r = ingest::ingerir(db, &p);
        let f = search::una(db, r[0].id.as_ref().unwrap()).unwrap().unwrap();
        assert_eq!(f.tipo, "document");
        assert_eq!(f.title, "Lo llamo yo");
        //  Pero de dónde viene se sigue sabiendo.
        assert_eq!(f.source, "youtube");
    });
}

// ── las carpetas tuyas ───────────────────────────────────────────
//
//  Las tres de fábrica no son «las carpetas»: son un ejemplo. Lo que hace que
//  esto sea tuyo es poder hacerte las que quieras, ponerles el nombre que
//  quieras y quitarlas sin perder lo que había dentro.

fn carpeta(db: &rusqlite::Connection, params: serde_json::Value) -> proto::Respuesta {
    proto::despachar(
        db,
        &proto::Peticion { v: 1, id: "c".into(), method: "space_put".into(), params },
    )
}

#[test]
fn una_carpeta_se_hace_antes_de_tener_que_meter() {
    banco(|db| {
        //  Vacía y ya existe: es la diferencia entre una carpeta y una etiqueta
        //  que aparece sola. Una que se crea al meter algo y desaparece al
        //  sacarlo no es un sitio donde guardar, es un efecto secundario.
        let r = carpeta(db, serde_json::json!({ "name": "La mudanza" }));
        assert!(r.ok, "{:?}", r.error);
        let secciones = search::secciones(db).unwrap();
        let mia = secciones.iter().find(|s| s.name == "La mudanza").expect("no está");
        assert_eq!(mia.id, "la-mudanza", "el id sale del nombre y es un id");
        assert_eq!(mia.count, 0);
    });
}

//  Los acentos y los espacios no llegan al id. Viaja en el filtro de la página
//  y en la línea de órdenes, y uno con tildes hay que escaparlo en cada sitio.
#[test]
fn el_id_de_una_carpeta_es_un_id() {
    for (nombre, id) in [
        ("Cosas de casa", "cosas-de-casa"),
        ("Investigación", "investigacion"),
        ("  Año  nuevo  ", "ano-nuevo"),
        ("¿Qué leo?", "que-leo"),
        ("C++", "c"),
    ] {
        assert_eq!(ingest::id_de_espacio(nombre), id, "con «{}»", nombre);
    }
}

//  Renombrar es renombrar, no crear otra al lado.
#[test]
fn renombrar_una_carpeta_no_hace_otra() {
    banco(|db| {
        carpeta(db, serde_json::json!({ "name": "Cosas" }));
        let id = ingest::ingerir(db, &texto("algo dentro"))[0].id.clone().unwrap();
        proto::despachar(db, &proto::Peticion {
            v: 1, id: "a".into(), method: "annotate".into(),
            params: serde_json::json!({ "id": id, "space": "cosas" }),
        });

        let r = carpeta(db, serde_json::json!({ "id": "cosas", "name": "Cosas de casa" }));
        assert!(r.ok, "{:?}", r.error);

        let secciones = search::secciones(db).unwrap();
        let carpetas: Vec<_> = secciones.iter().filter(|s| s.kind == "space").collect();
        assert_eq!(carpetas.iter().filter(|s| s.id == "cosas").count(), 1);
        let mia = carpetas.iter().find(|s| s.id == "cosas").unwrap();
        assert_eq!(mia.name, "Cosas de casa");
        //  Y lo de dentro sigue dentro: el id no se ha movido.
        assert_eq!(mia.count, 1);
    });
}

//  Y quitar la carpeta no quema los libros.
#[test]
fn quitar_una_carpeta_no_borra_lo_que_habia() {
    banco(|db| {
        let id = ingest::ingerir(db, &texto("un apunte")) [0].id.clone().unwrap();
        proto::despachar(db, &proto::Peticion {
            v: 1, id: "a".into(), method: "annotate".into(),
            params: serde_json::json!({ "id": id, "space": "La mudanza" }),
        });
        assert_eq!(search::listar(db, 10, None, &search::Filtro {
            space: Some("la-mudanza".into()), ..Default::default()
        }).unwrap().len(), 1);

        let r = proto::despachar(db, &proto::Peticion {
            v: 1, id: "d".into(), method: "space_delete".into(),
            params: serde_json::json!({ "id": "la-mudanza" }),
        });
        assert!(r.ok, "{:?}", r.error);

        //  La carpeta ya no está…
        assert!(!search::secciones(db).unwrap().iter().any(|s| s.id == "la-mudanza"));
        //  …y lo que tenía dentro sigue en la biblioteca.
        assert_eq!(search::cuentas(db).unwrap().captures, 1);
        assert!(search::una(db, &id).unwrap().is_some());
    });
}

//  Mover algo a una carpeta que ya existe no le cambia el nombre. Es el fallo
//  que tendría cualquiera que mandara el id como si fuera el nombre.
#[test]
fn mover_por_id_respeta_el_nombre_de_la_carpeta() {
    banco(|db| {
        let id = ingest::ingerir(db, &texto("a leer"))[0].id.clone().unwrap();
        proto::despachar(db, &proto::Peticion {
            v: 1, id: "a".into(), method: "annotate".into(),
            params: serde_json::json!({ "id": id, "space": "leer-luego" }),
        });
        let s = search::secciones(db).unwrap();
        let leer = s.iter().find(|s| s.id == "leer-luego").unwrap();
        assert_eq!(leer.name, "Leer luego", "el id se coló como nombre");
        assert_eq!(leer.count, 1);
    });
}

// ── lo que se sabe de fuera ──────────────────────────────────────
//
//  El worker no sale a la red y no va a salir. Lo que trae la casa entra por
//  `enrich`, y lo que se prueba aquí es la única regla que importa de ese
//  método: qué pisa y qué no.

fn enriquecer(db: &rusqlite::Connection, id: &str, params: serde_json::Value) -> proto::Respuesta {
    let mut v = params;
    v["id"] = serde_json::json!(id);
    proto::despachar(
        db,
        &proto::Peticion { v: 1, id: "e".into(), method: "enrich".into(), params: v },
    )
}

//  Un enlace guardado se titula con su dominio. Eso es un apaño, y la portada
//  de la página lo puede pisar.
#[test]
fn la_portada_pisa_el_titulo_de_apano() {
    banco(|db| {
        let r = ingest::ingerir(db, &url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"));
        let id = r[0].id.clone().unwrap();
        //  De momento no se sabe cómo se llama.
        assert_eq!(search::una(db, &id).unwrap().unwrap().title,
                   "https://youtube.com/watch?v=dQw4w9WgXcQ");

        let resp = enriquecer(db, &id, serde_json::json!({
            "title": "Rick Astley - Never Gonna Give You Up",
            "author": "Rick Astley",
            "excerpt": "El vídeo oficial.",
            "preview_b64": util::a_base64(b"unos bytes de imagen"),
        }));
        assert!(resp.ok, "{:?}", resp.error);

        let f = search::una(db, &id).unwrap().unwrap();
        assert_eq!(f.title, "Rick Astley - Never Gonna Give You Up");
        assert_eq!(f.author, "Rick Astley");
        assert_eq!(f.excerpt, "El vídeo oficial.");
        //  Y la miniatura, ya montada: quien la dibuja recibe una ruta, no un
        //  hash.
        let foto = f.preview_path.expect("tendría que haber miniatura");
        assert!(std::path::Path::new(&foto).exists(), "la miniatura no está en el disco");
        //  Se busca por el título nuevo, que es la prueba de que se reindexó.
        assert_eq!(search::buscar(db, "astley", 10).unwrap().len(), 1);
    });
}

//  Y lo guardado dice a qué dirección hay que salir a por su portada. Sin eso,
//  quien acaba de guardar tiene el id y no sabe adónde ir.
#[test]
fn lo_guardado_dice_de_que_direccion_era() {
    banco(|db| {
        let r = ingest::ingerir(db, &url("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=9"));
        //  La canónica y no la de origen: es la que hay que visitar.
        assert_eq!(r[0].url.as_deref(), Some("https://youtube.com/watch?v=dQw4w9WgXcQ"));
        //  Y un texto suelto no tiene ninguna, que también hay que poder decirlo.
        assert_eq!(ingest::ingerir(db, &texto("sin dirección"))[0].url, None);
    });
}

//  El cuerpo de la página se guarda Y SE BUSCA.
//
//  Es la diferencia entre una biblioteca que sabe de títulos y una que sabe de
//  lo que hay dentro: sin esto, buscar una frase de un artículo que guardaste
//  no encuentra nada, ni tú ni la IA.
#[test]
fn el_cuerpo_de_lo_guardado_se_indexa() {
    banco(|db| {
        let id = ingest::ingerir(db, &url("https://ejemplo.com/articulo"))[0]
            .id.clone().unwrap();
        //  De momento no hay nada que buscar dentro.
        assert_eq!(search::buscar(db, "cerámica", 10).unwrap().len(), 0);

        assert!(enriquecer(db, &id, serde_json::json!({
            "title": "Cómo cocer barro",
            "text": "La cerámica de baja temperatura pide un esmalte distinto.",
        })).ok);

        //  Por una palabra que solo está en el cuerpo.
        assert_eq!(search::buscar(db, "esmalte", 10).unwrap().len(), 1);
        //  Y el extracto se ha llenado con el principio, que es lo que se
        //  enseña en la tarjeta y lo que ve el modelo.
        let f = search::una(db, &id).unwrap().unwrap();
        assert!(f.excerpt.starts_with("La cerámica"), "{:?}", f.excerpt);
    });
}

//  Y no se relee: una captura cuyo texto cambia sola deja de ser una copia de
//  lo que viste. Volver a leer la página dentro de un mes traería otra cosa.
#[test]
fn el_cuerpo_guardado_no_se_reescribe() {
    banco(|db| {
        let id = ingest::ingerir(db, &url("https://ejemplo.com/x"))[0].id.clone().unwrap();
        assert!(enriquecer(db, &id, serde_json::json!({ "text": "lo que decía entonces" })).ok);
        assert!(enriquecer(db, &id, serde_json::json!({ "text": "lo que dice hoy" })).ok);
        assert_eq!(search::buscar(db, "entonces", 10).unwrap().len(), 1);
        assert_eq!(search::buscar(db, "hoy", 10).unwrap().len(), 0);
    });
}

//  Y un texto que llegó con el arrastre tampoco se pisa: eso es lo que
//  seleccionaste tú.
#[test]
fn el_texto_que_trajiste_manda() {
    banco(|db| {
        let id = ingest::ingerir(db, &texto("esto lo seleccioné yo"))[0].id.clone().unwrap();
        assert!(enriquecer(db, &id, serde_json::json!({ "text": "otra cosa distinta" })).ok);
        assert_eq!(search::buscar(db, "seleccioné", 10).unwrap().len(), 1);
        assert_eq!(search::buscar(db, "distinta", 10).unwrap().len(), 0);
    });
}

//  Y NO pisa el que traía el arrastre. Un navegador manda el título de la
//  pestaña al soltar; ese lo puso el mismo sitio y vale igual.
#[test]
fn la_portada_no_pisa_el_titulo_que_traia_el_arrastre() {
    banco(|db| {
        let mut p = url("https://ejemplo.com/articulo");
        p.title = Some("Como lo llamé yo".into());
        let id = ingest::ingerir(db, &p)[0].id.clone().unwrap();

        let resp = enriquecer(db, &id, serde_json::json!({
            "title": "El título de la página", "author": "Alguien",
        }));
        assert!(resp.ok, "{:?}", resp.error);
        let f = search::una(db, &id).unwrap().unwrap();
        assert_eq!(f.title, "Como lo llamé yo");
        //  Pero el autor, que no había, sí entra: ahí no se pisa nada.
        assert_eq!(f.author, "Alguien");
    });
}

//  Lo tuyo no se toca nunca, y enriquecer dos veces no cambia lo de la primera.
#[test]
fn enriquecer_no_toca_lo_tuyo_ni_se_repite() {
    banco(|db| {
        let id = ingest::ingerir(db, &url("https://ejemplo.com/x"))[0].id.clone().unwrap();
        proto::despachar(db, &proto::Peticion {
            v: 1, id: "a".into(), method: "annotate".into(),
            params: serde_json::json!({ "id": id, "note": "mío", "tags": ["azul"] }),
        });

        assert!(enriquecer(db, &id, serde_json::json!({
            "title": "La primera", "author": "Uno",
            "preview_b64": util::a_base64(b"la primera foto"),
        })).ok);
        let primera = search::una(db, &id).unwrap().unwrap();

        assert!(enriquecer(db, &id, serde_json::json!({
            "title": "La segunda", "author": "Otro",
            "preview_b64": util::a_base64(b"otra foto distinta"),
        })).ok);
        let f = search::una(db, &id).unwrap().unwrap();

        assert_eq!(f.note, "mío");
        assert_eq!(f.tags, vec!["azul".to_string()]);
        //  La segunda no pisa: el título ya no es de apaño, el autor ya estaba
        //  y la miniatura también.
        assert_eq!(f.title, "La primera");
        assert_eq!(f.author, "Uno");
        assert_eq!(f.preview_path, primera.preview_path);
    });
}

//  Un fichero guardado sale en la lista de pendientes con SU RUTA, para que
//  alguien pueda abrirlo y sacarle el texto.
//
//  Sin esto, un PDF de cuarenta páginas se queda para siempre siendo una fila
//  que dice «informe.pdf»: no se busca por dentro y la IA ve el nombre otra vez.
#[test]
fn un_fichero_sin_texto_sale_con_su_ruta() {
    banco(|db| {
        let f = std::env::temp_dir().join(format!("deriva-{}.pdf", util::ahora_ms()));
        std::fs::write(&f, b"%PDF-1.4 lo que sea").unwrap();

        let p = ingest::Peticion {
            tipo: "document".into(),
            paths: vec![f.to_string_lossy().to_string()],
            ..Default::default()
        };
        let id = ingest::ingerir(db, &p)[0].id.clone().unwrap();

        let pendientes = search::por_enriquecer(db, 10).unwrap();
        let mio = pendientes.iter().find(|x| x.id == id).expect("no sale el fichero");
        let ruta = mio.path.as_deref().expect("sale sin ruta que abrir");
        assert!(std::path::Path::new(ruta).exists(), "la ruta no lleva a ningún sitio");

        //  Y cuando ya se ha leído, deja de salir por eso.
        assert!(enriquecer(db, &id, serde_json::json!({
            "text": "lo que ponía el pdf",
        })).ok);
        let pendientes = search::por_enriquecer(db, 10).unwrap();
        assert!(pendientes.iter().all(|x| x.path.is_none() || x.id != id),
                "vuelve a pedir que se abra un fichero que ya se leyó");
        //  Y se busca por dentro.
        assert_eq!(search::buscar(db, "ponía", 10).unwrap().len(), 1);
    });
}

//  Una captura de antes de los adaptadores aprende de dónde venía.
//
//  No hay nada que preguntarle a nadie: está en su propia dirección. Lo que
//  faltaba era el momento de mirarla, y ese momento es cuando alguien vuelve a
//  pasar por ella.
#[test]
fn al_enriquecer_tambien_se_aprende_de_donde_venia() {
    banco(|db| {
        let id = ingest::ingerir(db, &url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))[0]
            .id.clone().unwrap();
        //  Se le quita, como si la hubiera guardado el worker de la semana
        //  pasada.
        db.execute("UPDATE captures SET source = '', type = 'url' WHERE id = ?1", [&id])
            .unwrap();

        assert!(enriquecer(db, &id, serde_json::json!({ "author": "Alguien" })).ok);
        let f = search::una(db, &id).unwrap().unwrap();
        assert_eq!(f.source, "youtube");
        assert_eq!(f.tipo, "video", "un enlace de YouTube es un vídeo");
    });
}

//  Pero no le cambia el tipo a quien ya lo tenía dicho.
#[test]
fn aprender_de_donde_venia_no_pisa_el_tipo() {
    banco(|db| {
        let mut p = url("https://www.youtube.com/watch?v=dQw4w9WgXcQ");
        p.tipo = "document".into();
        let id = ingest::ingerir(db, &p)[0].id.clone().unwrap();
        db.execute("UPDATE captures SET source = '' WHERE id = ?1", [&id]).unwrap();

        assert!(enriquecer(db, &id, serde_json::json!({ "author": "Alguien" })).ok);
        let f = search::una(db, &id).unwrap().unwrap();
        assert_eq!(f.source, "youtube");
        assert_eq!(f.tipo, "document");
    });
}

//  Lo que sigue sin portada se puede volver a intentar.
//
//  Sin esto, lo guardado antes de que existiera el enriquecimiento —o cuando no
//  había red— se queda para siempre con una dirección cruda por título, que es
//  justo el problema que el enriquecimiento venía a resolver.
#[test]
fn se_sabe_lo_que_sigue_sin_portada() {
    banco(|db| {
        let a = ingest::ingerir(db, &url("https://ejemplo.com/uno"))[0].id.clone().unwrap();
        let b = ingest::ingerir(db, &url("https://ejemplo.com/dos"))[0].id.clone().unwrap();
        //  Un texto no tiene página a la que ir.
        ingest::ingerir(db, &texto("esto no sale a ningún sitio"));

        //  De momento les falta a las dos.
        let pendientes = search::por_enriquecer(db, 10).unwrap();
        assert_eq!(pendientes.len(), 2);
        //  Y con la dirección, que es lo que hace falta para ir.
        assert!(pendientes
            .iter()
            .any(|p| p.id == a && p.url.as_deref().is_some_and(|u| u.starts_with("http"))));

        //  A una se le da todo: título de verdad, miniatura y el texto de
        //  dentro. Las tres cosas, porque a medias sigue estando a medias.
        assert!(enriquecer(db, &a, serde_json::json!({
            "title": "Un título de verdad",
            "preview_b64": util::a_base64(b"una foto"),
            "text": "el cuerpo del artículo, entero",
        })).ok);
        let pendientes = search::por_enriquecer(db, 10).unwrap();
        assert_eq!(pendientes.len(), 1, "la enriquecida no puede seguir pendiente");
        assert_eq!(pendientes[0].id, b);

        //  Con miniatura pero con el título de apaño sigue pendiente: son
        //  maneras distintas de estar a medias.
        assert!(enriquecer(db, &b, serde_json::json!({
            "preview_b64": util::a_base64(b"otra foto"),
            "text": "algo de texto",
        })).ok);
        assert_eq!(search::por_enriquecer(db, 10).unwrap().len(), 1);

        //  Y lo tirado a la papelera no se va a buscar.
        proto::despachar(db, &proto::Peticion {
            v: 1, id: "t".into(), method: "trash".into(),
            params: serde_json::json!({ "id": b }),
        });
        assert_eq!(search::por_enriquecer(db, 10).unwrap().len(), 0);
    });
}

//  Una miniatura ilegible no deja la captura a medias: se rechaza entera y lo
//  de dentro se queda como estaba.
#[test]
fn una_miniatura_ilegible_no_escribe_nada() {
    banco(|db| {
        let id = ingest::ingerir(db, &url("https://ejemplo.com/y"))[0].id.clone().unwrap();
        let resp = enriquecer(db, &id, serde_json::json!({
            "title": "No debería entrar", "preview_b64": "esto no es base64 ~~~",
        }));
        assert!(!resp.ok);
        let f = search::una(db, &id).unwrap().unwrap();
        assert_eq!(f.title, "ejemplo.com", "se escribió el título pese al fallo");
        assert!(f.preview_path.is_none());
    });
}

//  Con todas las palabras primero, y con cualquiera si así no sale nada.
//
//  El AND implícito es lo correcto mientras encuentre algo, y es lo peor que
//  puede pasar cuando no: basta que una palabra de cuatro no esté para que la
//  respuesta sea «no hay nada guardado que se parezca a eso», que es mentira. Y
//  falla justo cuando más material hay, porque cuanto más grande es la
//  biblioteca más larga es la pregunta que le haces.
#[test]
fn si_con_todas_las_palabras_no_sale_nada_vale_con_una() {
    banco(|db| {
        let mut p = texto("Fondos de pantalla animados para Wayland");
        p.title = Some("live-paper".into());
        ingest::ingerir(db, &p);
        ingest::ingerir(db, &texto("Una receta de bizcocho"));

        //  Con todas: encuentra.
        assert_eq!(search::buscar(db, "fondos pantalla", 10).unwrap().len(), 1);
        //  Con una que no está, el AND no encontraría nada y sin embargo hay
        //  algo que se parece bastante.
        let r = search::buscar(db, "fondos de pantalla para escritorio", 10).unwrap();
        assert_eq!(r.len(), 1, "la respuesta era «no hay nada» y sí lo había");
        assert_eq!(r[0].title, "live-paper");

        //  Y lo que no se parece en nada sigue sin salir: el repesque es para
        //  no mentir, no para contestar cualquier cosa.
        assert_eq!(search::buscar(db, "termodinámica", 10).unwrap().len(), 0);
    });
}

//  Y una pregunta entera no se trata como un montón de palabras sueltas.
//
//  Es lo que llega desde el chat: la IA pasa lo que le has dicho tal cual y en
//  español eso es «¿tengo algo guardado sobre…?». Sin quitar el relleno, el
//  repesque devuelve media biblioteca por «tengo» y por «algo», y una respuesta
//  con todo dentro es tan inútil como una vacía.
#[test]
fn una_pregunta_entera_no_arrastra_media_biblioteca() {
    banco(|db| {
        let mut p = texto("Fondos de pantalla animados para Wayland");
        p.title = Some("live-paper".into());
        ingest::ingerir(db, &p);
        let mut p = texto("Tengo que acordarme de algo sobre el bizcocho");
        p.title = Some("receta".into());
        ingest::ingerir(db, &p);

        let r = search::buscar(db, "¿tengo algo guardado sobre fondos de pantalla?", 10).unwrap();
        assert_eq!(r.len(), 1, "el relleno arrastró lo que no era");
        assert_eq!(r[0].title, "live-paper");
    });
}

//  Y con una sola palabra no hay repesque que hacer: sería la misma consulta.
#[test]
fn con_una_palabra_no_hay_segunda_vuelta() {
    assert_eq!(search::consulta_fts_floja("wallpapers"), None);
    //  Y las palabras cortas o de relleno no entran en el repesque: «de» está
    //  en todo lo que has guardado, y «tengo» y «sobre» también.
    assert_eq!(search::consulta_fts_floja("fondos de pantalla").unwrap(),
               "\"fondos\"* OR \"pantalla\"*");
    //  La consulta conserva la palabra tal cual —el índice ya quita las
    //  tildes—; lo que se pliega es solo la comparación con la lista.
    assert_eq!(search::consulta_fts_floja("tengo algo sobre cerámica antigua").unwrap(),
               "\"cerámica\"* OR \"antigua\"*");
    assert_eq!(search::consulta_fts_floja("tenía algún apunte de cerámica").unwrap(),
               "\"apunte\"* OR \"cerámica\"*");
    //  Salvo que no quede otra: más vale de más que nada.
    assert_eq!(search::consulta_fts_floja("de la").unwrap(), "\"de\"* OR \"la\"*");
    assert_eq!(search::consulta_fts_floja("tengo algo").unwrap(), "\"tengo\"* OR \"algo\"*");
}

// ── el parecido por significado ──────────────────────────────────
//
//  El modelo son 506 MB y es opcional, así que estas pruebas corren SIN él: lo
//  que comprueban es que sin modelo la biblioteca funciona exactamente igual, y
//  que las piezas que no necesitan modelo —guardar un vector, compararlo,
//  decidir con qué texto se representa una captura— hacen lo que dicen.
//
//  La calidad del parecido no se prueba aquí y no se puede: depende del modelo,
//  y un número clavado en una prueba se convierte en una prueba que falla el
//  día que se cambie por uno mejor.

#[test]
fn sin_modelo_la_biblioteca_busca_igual() {
    banco(|db| {
        let mut p = texto("Fondos de pantalla animados para Wayland");
        p.title = Some("live-paper".into());
        ingest::ingerir(db, &p);

        //  En el banco no hay modelo: nada de vectores y ni un fallo.
        assert!(!vectores::listo(), "el banco no puede depender de un modelo");
        assert_eq!(search::parecidas(db, "fondos", 5).unwrap().len(), 0);
        let (hechas, faltan) = search::vectorizar_pendientes(db, 10).unwrap();
        assert_eq!((hechas, faltan), (0, 0));

        //  Y la búsqueda de siempre, intacta.
        assert_eq!(search::buscar(db, "wayland", 5).unwrap().len(), 1);
    });
}

//  Sin material no hay vector, y eso no es una optimización.
//
//  Una captura de Reddit se quedó con seis caracteres de contenido —esa página
//  no da texto a quien no ejecuta JavaScript— y su vector, hecho de la palabra
//  «Reddit», aterrizaba en una zona genérica: se parecía un 0,26 a «repostería»
//  y un 0,24 a «editar vídeo». Salía en TODAS las búsquedas.
//
//  Un vector de una palabra no resume nada; es ruido con forma de resultado.
#[test]
fn una_captura_sin_apenas_texto_no_lleva_vector() {
    banco(|db| {
        let mut flaca = ingest::Peticion {
            tipo: "url".into(),
            source_url: Some("https://ejemplo.com/vacia".into()),
            ..Default::default()
        };
        flaca.title = Some("Web".into());
        let flaco = ingest::ingerir(db, &flaca)[0].id.clone().unwrap();
        let gordo = ingest::ingerir(db, &texto(
            "Fondos de pantalla animados para Wayland, escritos en Rust")) [0]
            .id.clone().unwrap();

        //  Sin modelo no hay nada que probar de los vectores, pero sí la
        //  criba: es la misma consulta la que elige a quién le toca.
        let (_, _) = search::vectorizar_pendientes(db, 10).unwrap();
        //  La regla, medida directamente sobre el texto que representaría a
        //  cada una.
        let de = |id: &str| {
            let f = search::una(db, id).unwrap().unwrap();
            vectores::texto_de(&f.title, &f.summary, "", &f.excerpt, "")
        };
        assert!(de(&flaco).chars().count() < search::MATERIAL_MINIMO,
                "«{}» daría para un vector", de(&flaco));
        assert!(de(&gordo).chars().count() >= search::MATERIAL_MINIMO);
    });
}

//  Un vector va y vuelve del disco tal cual. Se guarda crudo —`f32` little
//  endian— y no en JSON: un vector es una lista de números y meterlo en texto
//  lo hace cuatro veces más grande para tener que parsearlo en cada comparación.
#[test]
fn un_vector_va_y_vuelve_del_disco() {
    let v = vec![0.5f32, -0.25, 0.0, 1.0];
    let b = vectores::a_bytes(&v);
    assert_eq!(b.len(), 16);
    assert_eq!(vectores::de_bytes(&b), v);
}

//  Y dos vectores de medidas distintas NO se comparan hasta donde alcancen: eso
//  no da un error, da un parecido inventado, que es peor.
#[test]
fn dos_vectores_de_modelos_distintos_no_se_parecen() {
    let a = vec![1.0f32, 0.0];
    assert_eq!(vectores::parecido(&a, &[1.0, 0.0]), 1.0);
    assert!(vectores::parecido(&a, &[0.0, 1.0]).abs() < 0.001);
    assert_eq!(vectores::parecido(&a, &[1.0, 0.0, 0.0]), -1.0, "medidas distintas");
    assert_eq!(vectores::parecido(&[], &[]), -1.0);
}

//  Con qué se representa una captura: lo que la describe, no todo lo que dice.
//  Un vector es una media, y la media de cuarenta páginas se parece un poco a
//  todo y mucho a nada.
#[test]
fn una_captura_se_representa_por_lo_que_la_describe() {
    let t = vectores::texto_de("Cómo cocer barro", "Sobre cerámica de baja temperatura.",
                               "ceramica, manualidades", "El horno...", "");
    assert!(t.starts_with("Cómo cocer barro"));
    assert!(t.contains("cerámica"));
    assert!(t.contains("ceramica, manualidades"));

    //  El cuerpo solo entra cuando lo demás no llena: si ya hay título y
    //  resumen, el artículo entero estorba.
    let corto = vectores::texto_de("Título", "", "", "", &"palabra ".repeat(500));
    assert!(corto.chars().count() <= 1200);
    assert!(corto.contains("palabra"));
    let lleno = vectores::texto_de("Título", &"resumen largo ".repeat(40), "", "",
                                   "ESTE CUERPO NO DEBERIA ENTRAR");
    assert!(!lleno.contains("NO DEBERIA"));
}

// ── lo que entendió la IA ────────────────────────────────────────
//
//  Aquí no hay modelo ninguno: el resumen entra ya escrito, igual que entran
//  ya leídos los metadatos de una página. Lo que se prueba es la única regla
//  que importa de `classify`, que es más estricta que la de `enrich` porque un
//  título de una página es un hecho y esto es una opinión.

fn clasificar(db: &rusqlite::Connection, id: &str, params: serde_json::Value) -> proto::Respuesta {
    let mut v = params;
    v["id"] = serde_json::json!(id);
    proto::despachar(
        db,
        &proto::Peticion { v: 1, id: "k".into(), method: "classify".into(), params: v },
    )
}

//  Lo que entiende se guarda, y se BUSCA: un resumen que no está en el índice
//  no lo encuentra nadie, ni tú ni la IA, y entonces no sirve para nada.
#[test]
fn el_resumen_se_guarda_y_se_busca() {
    banco(|db| {
        let id = ingest::ingerir(db, &texto("un texto larguísimo sobre cerámica"))[0]
            .id.clone().unwrap();
        let r = clasificar(db, &id, serde_json::json!({
            "summary": "Explica cómo se cuece el barro a baja temperatura.",
            "tags": ["ceramica", "manualidades"],
        }));
        assert!(r.ok, "{:?}", r.error);

        let f = search::una(db, &id).unwrap().unwrap();
        assert_eq!(f.summary, "Explica cómo se cuece el barro a baja temperatura.");
        assert_eq!(f.tags, vec!["ceramica".to_string(), "manualidades".to_string()]);
        //  Y por una palabra que SOLO está en el resumen.
        assert_eq!(search::buscar(db, "cuece", 10).unwrap().len(), 1);
        assert_eq!(search::buscar(db, "barro", 10).unwrap().len(), 1);
    });
}

//  Las etiquetas se SUMAN. `annotate` reemplaza porque ahí el que escribe eres
//  tú; borrar las tuyas para poner las suyas sería que la IA te ordena el
//  armario a su gusto.
#[test]
fn la_ia_suma_etiquetas_y_no_borra_las_tuyas() {
    banco(|db| {
        let id = ingest::ingerir(db, &texto("algo"))[0].id.clone().unwrap();
        proto::despachar(db, &proto::Peticion {
            v: 1, id: "a".into(), method: "annotate".into(),
            params: serde_json::json!({ "id": id, "tags": ["mías"], "note": "para el jueves" }),
        });

        assert!(clasificar(db, &id, serde_json::json!({
            "summary": "Un resumen.", "tags": ["suya"],
        })).ok);

        let f = search::una(db, &id).unwrap().unwrap();
        assert_eq!(f.tags, vec!["mías".to_string(), "suya".to_string()]);
        assert_eq!(f.note, "para el jueves", "la nota es tuya y no la toca nadie");
    });
}

//  Y no reescribe lo que ya había resumido: lo que leíste ayer no puede decir
//  otra cosa hoy sin que tú hayas tocado nada.
#[test]
fn el_resumen_no_se_reescribe() {
    banco(|db| {
        let id = ingest::ingerir(db, &texto("algo"))[0].id.clone().unwrap();
        assert!(clasificar(db, &id, serde_json::json!({ "summary": "El primero." })).ok);
        assert!(clasificar(db, &id, serde_json::json!({ "summary": "Otro distinto." })).ok);
        assert_eq!(search::una(db, &id).unwrap().unwrap().summary, "El primero.");
    });
}

//  La carpeta, solo si estaba suelta. Moverte algo de sitio es la clase de
//  ayuda que hace que no encuentres tus cosas.
#[test]
fn la_ia_no_te_mueve_lo_que_ya_habias_colocado() {
    banco(|db| {
        let suelta = ingest::ingerir(db, &texto("sin sitio"))[0].id.clone().unwrap();
        let colocada = ingest::ingerir(db, &texto("con sitio"))[0].id.clone().unwrap();
        proto::despachar(db, &proto::Peticion {
            v: 1, id: "a".into(), method: "annotate".into(),
            params: serde_json::json!({ "id": colocada, "space": "proyectos" }),
        });

        let r = clasificar(db, &suelta, serde_json::json!({ "space": "inspiracion" }));
        assert_eq!(r.result.as_ref().unwrap()["moved"], serde_json::json!(true));
        let r = clasificar(db, &colocada, serde_json::json!({ "space": "inspiracion" }));
        assert_eq!(r.result.as_ref().unwrap()["moved"], serde_json::json!(false));

        assert_eq!(search::listar(db, 10, None, &search::Filtro {
            space: Some("proyectos".into()), ..Default::default()
        }).unwrap().len(), 1, "le cambiaron la carpeta");
    });
}

//  Lo que no se puede resumir NO se vuelve a preguntar.
//
//  Es el fallo que se vio en vivo: una página de Reddit que no da texto a quien
//  no ejecuta JavaScript se quedó de pendiente eterna, y cada veinte segundos
//  se le volvía a preguntar al modelo —que hacía bien en callarse— pagando cada
//  vez. «No se pudo decir nada» es una respuesta y hay que recordarla.
#[test]
fn lo_que_no_se_puede_resumir_no_se_pregunta_para_siempre() {
    banco(|db| {
        let id = ingest::ingerir(db, &url("https://ejemplo.com/vacia"))[0].id.clone().unwrap();
        assert_eq!(search::por_clasificar(db, 10).unwrap().len(), 1);

        //  Se le pregunta y el modelo no sabe decir nada: `classify` sin nada
        //  dentro es exactamente eso.
        assert!(clasificar(db, &id, serde_json::json!({})).ok);

        assert_eq!(search::por_clasificar(db, 10).unwrap().len(), 0,
                   "se volvería a preguntar lo mismo cada vez");
        //  Y la cuenta que ve el usuario baja: si no, la página dice «queda 1
        //  por resumir» para siempre.
        assert_eq!(search::cuentas(db).unwrap().pending_summary, 0);
    });
}

//  Pero si LO QUE HAY que mirar cambia, se vuelve a mirar. Se miró con un
//  título y ahora hay un artículo entero: es otro material.
#[test]
fn si_llega_el_texto_se_vuelve_a_mirar() {
    banco(|db| {
        let id = ingest::ingerir(db, &url("https://ejemplo.com/tarde"))[0].id.clone().unwrap();
        assert!(clasificar(db, &id, serde_json::json!({})).ok);
        assert_eq!(search::por_clasificar(db, 10).unwrap().len(), 0);

        //  Llega el cuerpo de la página.
        assert!(enriquecer(db, &id, serde_json::json!({
            "text": "un artículo entero sobre cerámica",
        })).ok);
        assert_eq!(search::por_clasificar(db, 10).unwrap().len(), 1,
                   "con material nuevo hay que volver a mirarlo");
    });
}

//  Y se sabe lo que falta por mirar, con lo justo para poder resumirlo: el
//  título, de dónde viene y un trozo. NO el contenido entero.
#[test]
fn lo_que_falta_por_resumir_sale_recortado() {
    banco(|db| {
        let largo = "palabra ".repeat(400);
        let id = ingest::ingerir(db, &texto(&largo))[0].id.clone().unwrap();
        let faltan = search::por_clasificar(db, 10).unwrap();
        assert_eq!(faltan.len(), 1);
        assert_eq!(faltan[0].id, id);
        assert!(faltan[0].excerpt.chars().count() <= 400,
                "sale más texto del equipo del necesario");

        assert!(clasificar(db, &id, serde_json::json!({ "summary": "Ya está." })).ok);
        assert_eq!(search::por_clasificar(db, 10).unwrap().len(), 0);
    });
}

//  Las etiquetas que ya usas, para poder enseñarlas y para poder decirle a la
//  IA que reutilice en vez de estrenar.
#[test]
fn se_pueden_listar_las_etiquetas_que_usas() {
    banco(|db| {
        let a = ingest::ingerir(db, &texto("uno"))[0].id.clone().unwrap();
        let b = ingest::ingerir(db, &texto("dos"))[0].id.clone().unwrap();
        for (id, ts) in [(&a, vec!["cocina", "recetas"]), (&b, vec!["cocina"])] {
            proto::despachar(db, &proto::Peticion {
                v: 1, id: "a".into(), method: "annotate".into(),
                params: serde_json::json!({ "id": id, "tags": ts }),
            });
        }
        let r = proto::despachar(db, &proto::Peticion {
            v: 1, id: "t".into(), method: "tags".into(), params: serde_json::json!({}),
        });
        assert!(r.ok, "{:?}", r.error);
        let v = r.result.unwrap();
        let lista = v["tags"].as_array().unwrap();
        //  La más usada primero: es la que más probabilidades tiene de volver a
        //  encajar, y la lista que se manda a un modelo va recortada.
        assert_eq!(lista[0]["name"], serde_json::json!("cocina"));
        assert_eq!(lista[0]["count"], serde_json::json!(2));
        assert_eq!(lista.len(), 2);

        //  Y una etiqueta que se queda sin nada no sale: sería ofrecerle al
        //  modelo un cajón vacío como si fuera una categoría en uso.
        proto::despachar(db, &proto::Peticion {
            v: 1, id: "a".into(), method: "annotate".into(),
            params: serde_json::json!({ "id": a, "tags": ["cocina"] }),
        });
        let r = proto::despachar(db, &proto::Peticion {
            v: 1, id: "t".into(), method: "tags".into(), params: serde_json::json!({}),
        });
        assert_eq!(r.result.unwrap()["tags"].as_array().unwrap().len(), 1);
    });
}

// ── la reaparición ───────────────────────────────────────────────
//
//  El motor es determinista, y eso es lo que se prueba: la misma biblioteca
//  devuelve lo mismo, y la razón que se enseña es literalmente la regla que
//  acertó.

fn aplazar(db: &rusqlite::Connection, id: &str, cuando: i64) {
    db.execute("UPDATE captures SET snoozed_until = ?2 WHERE id = ?1",
               rusqlite::params![id, cuando]).unwrap();
}

//  El orden de prioridad del plan, comprobado de arriba abajo: lo que pediste
//  tú manda sobre todo lo demás.
#[test]
fn lo_que_aplazaste_vuelve_antes_que_nada() {
    banco(|db| {
        //  Un favorito olvidado, que es la tercera prioridad.
        let viejo = ingest::ingerir(db, &texto("un favorito de hace mucho"))[0]
            .id.clone().unwrap();
        db.execute("UPDATE captures SET favorite = 1, captured_at = ?2 WHERE id = ?1",
                   rusqlite::params![viejo, util::ahora_ms() - 60 * 86_400_000i64]).unwrap();

        //  Y algo aplazado para ayer, que es la primera.
        let pedido = ingest::ingerir(db, &texto("esto lo aplacé yo"))[0].id.clone().unwrap();
        aplazar(db, &pedido, util::ahora_ms() - 86_400_000);

        let v = reaparicion::siguiente(db, None).unwrap().unwrap();
        assert_eq!(v.item.id, pedido);
        assert_eq!(v.reason, "scheduled");
        //  Y la razón se puede leer: si no se puede nombrar, no es elegible.
        assert!(!v.why.is_empty());
    });
}

//  Lo aplazado para el mes que viene no es elegible: aplazar es decir «ahora
//  no», y devolverlo igual sería no haber escuchado.
#[test]
fn lo_aplazado_para_luego_no_vuelve_todavia() {
    banco(|db| {
        let id = ingest::ingerir(db, &texto("para el mes que viene"))[0].id.clone().unwrap();
        aplazar(db, &id, util::ahora_ms() + 30 * 86_400_000);
        assert!(reaparicion::siguiente(db, None).unwrap().is_none());
    });
}

//  Lo que abriste hace nada tampoco: acabas de verlo.
#[test]
fn lo_recien_abierto_no_vuelve() {
    banco(|db| {
        let id = ingest::ingerir(db, &texto("lo miré ayer"))[0].id.clone().unwrap();
        db.execute("UPDATE captures SET last_opened_at = ?2 WHERE id = ?1",
                   rusqlite::params![id, util::ahora_ms() - 86_400_000i64]).unwrap();
        assert!(reaparicion::siguiente(db, None).unwrap().is_none());

        //  Pero pasada la semana, sí.
        db.execute("UPDATE captures SET last_opened_at = ?2 WHERE id = ?1",
                   rusqlite::params![id, util::ahora_ms() - 30 * 86_400_000i64]).unwrap();
        assert!(reaparicion::siguiente(db, None).unwrap().is_some());
    });
}

//  Y lo que se ha enseñado tres veces sin que nadie haga nada se calla. Es la
//  regla que impide que la misma tarjeta te persiga toda la semana.
#[test]
fn lo_que_se_ensena_y_nadie_toca_deja_de_salir() {
    banco(|db| {
        let id = ingest::ingerir(db, &texto("nadie me hace caso"))[0].id.clone().unwrap();
        for _ in 0..2 {
            reaparicion::apuntar_mostrada(db, &id, "old_random").unwrap();
        }
        assert!(reaparicion::siguiente(db, None).unwrap().is_some(), "dos todavía");
        reaparicion::apuntar_mostrada(db, &id, "old_random").unwrap();
        assert!(reaparicion::siguiente(db, None).unwrap().is_none(), "a la tercera, silencio");
    });
}

//  El contexto de aplicación es opt-in y llega de fuera: el worker no mira ni
//  una ventana. Lo que hace es preferir el espacio que le digan.
#[test]
fn el_espacio_de_la_aplicacion_manda_sobre_lo_antiguo() {
    banco(|db| {
        ingest::ingerir(db, &texto("algo viejo cualquiera"));
        let mut p = texto("los planos del proyecto");
        p.space = Some("Proyectos".into());
        let del_proyecto = ingest::ingerir(db, &p)[0].id.clone().unwrap();

        let v = reaparicion::siguiente(db, Some("proyectos")).unwrap().unwrap();
        assert_eq!(v.item.id, del_proyecto);
        assert_eq!(v.reason, "app_context");

        //  Sin decirle el espacio, gana la regla de siempre.
        let otra = reaparicion::siguiente(db, None).unwrap().unwrap();
        assert_ne!(otra.reason, "app_context");
    });
}

//  Y un espacio silenciado no devuelve nada. Silenciar es una manera de decir
//  «esto no me lo recuerdes», y hay que poder decirlo sin borrar nada.
#[test]
fn un_espacio_silenciado_no_devuelve_nada() {
    banco(|db| {
        let mut p = texto("cosas del trabajo");
        p.space = Some("Proyectos".into());
        ingest::ingerir(db, &p);
        assert!(reaparicion::siguiente(db, None).unwrap().is_some());

        db.execute("UPDATE spaces SET color = 'silenciado' WHERE id = 'proyectos'", [])
            .unwrap();
        assert!(reaparicion::siguiente(db, None).unwrap().is_none());
    });
}

#[test]
fn lo_que_hiciste_con_ella_se_apunta_una_vez() {
    banco(|db| {
        let id = ingest::ingerir(db, &texto("una cualquiera"))[0].id.clone().unwrap();
        let evento = reaparicion::apuntar_mostrada(db, &id, "old_random").unwrap();

        //  Un resultado que no existe no se guarda: la lista es cerrada.
        assert!(!reaparicion::apuntar_resultado(db, evento, "me_dio_igual").unwrap());
        assert!(reaparicion::apuntar_resultado(db, evento, "dismissed").unwrap());
        //  Y dos veces no: lo que ya se contestó no se recontesta.
        assert!(!reaparicion::apuntar_resultado(db, evento, "opened").unwrap());

        assert_eq!(reaparicion::descartes_seguidos(db).unwrap(), 1);
        assert_eq!(reaparicion::mostradas_hoy(db).unwrap(), 1);
    });
}

//  Tras dos descartes seguidos, silencio hasta mañana. La cuenta la lleva el
//  worker; el silencio lo aplica quien enseña, que es quien sabe qué hora es.
#[test]
fn los_descartes_seguidos_se_cuentan_y_se_cortan() {
    banco(|db| {
        let id = ingest::ingerir(db, &texto("una"))[0].id.clone().unwrap();
        for _ in 0..2 {
            let e = reaparicion::apuntar_mostrada(db, &id, "old_random").unwrap();
            reaparicion::apuntar_resultado(db, e, "dismissed").unwrap();
        }
        assert_eq!(reaparicion::descartes_seguidos(db).unwrap(), 2);

        //  Y uno que sí abriste rompe la racha: la cuenta es de SEGUIDOS.
        let e = reaparicion::apuntar_mostrada(db, &id, "old_random").unwrap();
        reaparicion::apuntar_resultado(db, e, "opened").unwrap();
        assert_eq!(reaparicion::descartes_seguidos(db).unwrap(), 0);
    });
}

//  Ignorarla cuenta igual que descartarla, y esta es la prueba del fallo que
//  la tenía saliendo tres veces al día durante cinco días seguidos.
//
//  Descartar a mano es abrir la página, elegir la tarjeta y pulsar un botón
//  pequeño. Nadie que no quiera la función hace ese viaje: la ignora y ya. Con
//  la cuenta mirando solo los resultados escritos, quince apariciones seguidas
//  dieron una racha de cero y el silencio no se activó jamás.
#[test]
fn ignorar_una_aparicion_cuenta_como_no_haber_servido() {
    banco(|db| {
        let id = ingest::ingerir(db, &texto("una"))[0].id.clone().unwrap();
        //  Enseñadas y no tocadas: sin resultado, que es como se quedan.
        reaparicion::apuntar_mostrada(db, &id, "old_random").unwrap();
        assert_eq!(reaparicion::descartes_seguidos(db).unwrap(), 1);
        reaparicion::apuntar_mostrada(db, &id, "old_random").unwrap();
        assert_eq!(reaparicion::descartes_seguidos(db).unwrap(), 2, "a la segunda, a callar");

        //  Y abrir una corta la racha aunque las de antes sigan sin resultado:
        //  que sirviera una vez es la señal contraria.
        let e = reaparicion::apuntar_mostrada(db, &id, "old_random").unwrap();
        reaparicion::apuntar_resultado(db, e, "opened").unwrap();
        assert_eq!(reaparicion::descartes_seguidos(db).unwrap(), 0);
    });
}

//  Y el silencio dura un día, no para siempre. Lo prometía el plan con esas
//  palabras y la consulta no miraba la fecha: una vez callada, callada para
//  el resto de la vida de la biblioteca.
#[test]
fn el_silencio_se_levanta_al_dia_siguiente() {
    banco(|db| {
        let id = ingest::ingerir(db, &texto("una"))[0].id.clone().unwrap();
        let anteayer = util::ahora_ms() - 2 * 86_400_000;
        for _ in 0..3 {
            db.execute("INSERT INTO revisit_events (capture_id, reason, shown_at) \
                        VALUES (?1, 'old_random', ?2)",
                       rusqlite::params![id, anteayer]).unwrap();
        }
        assert_eq!(reaparicion::descartes_seguidos(db).unwrap(), 0,
                   "lo de anteayer no puede seguir tapándole la boca hoy");
    });
}

//  Cuándo fue la última. Es lo que sustituye a la propiedad de QML que se
//  borraba en cada recarga y dejaba el hueco de media hora en nada.
#[test]
fn la_ultima_aparicion_sale_del_historial() {
    banco(|db| {
        assert_eq!(reaparicion::ultima_aparicion(db).unwrap(), 0,
                   "sin historial, cero: y cero deja pasar la primera");
        let id = ingest::ingerir(db, &texto("una"))[0].id.clone().unwrap();
        let antes = util::ahora_ms();
        reaparicion::apuntar_mostrada(db, &id, "old_random").unwrap();
        assert!(reaparicion::ultima_aparicion(db).unwrap() >= antes);
    });
}

//  Determinista: dos veces seguidas, lo mismo. Es lo que separa un motor que se
//  puede explicar de uno que hay que creerse.
#[test]
fn dos_veces_seguidas_devuelve_lo_mismo() {
    banco(|db| {
        for i in 0..12 {
            ingest::ingerir(db, &texto(&format!("cosa {}", i)));
        }
        let a = reaparicion::siguiente(db, None).unwrap().unwrap();
        let b = reaparicion::siguiente(db, None).unwrap().unwrap();
        assert_eq!(a.item.id, b.item.id);
        assert_eq!(a.reason, b.reason);
    });
}

// ── la salida de la fase ─────────────────────────────────────────

//  «Guardar, reiniciar y recuperar conserva todos los elementos.»
//
//  Reiniciar de verdad: se cierra la conexión y se abre otra sobre el mismo
//  disco, que es lo que pasa cuando Marea se recarga o el equipo se apaga. Si
//  algo viviera en memoria, aquí se caería.
#[test]
fn guardar_reiniciar_y_recuperar() {
    let _g = CERROJO.lock().unwrap_or_else(|e| e.into_inner());
    let mut b = [0u8; 8];
    util::azar(&mut b);
    let dir = std::env::temp_dir().join(format!("deriva-reinicio-{}", util::hex(&b)));
    std::env::set_var("MAREA_DERIVA_DIR", &dir);

    let f = std::env::temp_dir().join(format!("deriva-r-{}.bin", util::ahora_ms()));
    std::fs::write(&f, b"un adjunto que tiene que sobrevivir").unwrap();

    let mut ids = Vec::new();
    {
        let db = db::abrir().unwrap();
        for i in 0..25 {
            let mut p = texto(&format!("captura numero {} con la palabra pulpo", i));
            p.title = Some(format!("Nota {}", i));
            p.tags = vec!["prueba".into()];
            let r = ingest::ingerir(&db, &p);
            ids.push(r[0].id.clone().unwrap());
        }
        let p = ingest::Peticion {
            tipo: "document".into(),
            paths: vec![f.to_string_lossy().to_string()],
            ..Default::default()
        };
        ids.push(ingest::ingerir(&db, &p)[0].id.clone().unwrap());
        assert_eq!(search::cuentas(&db).unwrap().captures, 26);
    } //  aquí se cierra: se acabó el proceso, digamos.

    {
        let db = db::abrir().unwrap();
        assert_eq!(search::cuentas(&db).unwrap().captures, 26, "faltan capturas");
        assert_eq!(search::buscar(&db, "pulpo", 100).unwrap().len(), 25);
        assert_eq!(search::buscar(&db, "prueba", 100).unwrap().len(), 25);
        for id in &ids {
            assert!(search::una(&db, id).unwrap().is_some(), "se perdió {}", id);
        }
        //  Y el adjunto sigue en disco y sigue siendo el que era.
        let i = mantenimiento::integridad(&db, true).unwrap();
        assert!(i.ok, "{:?}", i);
    }

    let _ = std::fs::remove_file(&f);
    let _ = std::fs::remove_dir_all(&dir);
    std::env::remove_var("MAREA_DERIVA_DIR");
}

// ── buscar bien, no solo encontrar ──────────────────────────────

//  Lo que se ve primero es lo que se abre. Una palabra en el título de una
//  captura tiene que ganarle a la misma palabra perdida en el cuerpo de otra.
#[test]
fn el_titulo_pesa_mas_que_el_cuerpo() {
    banco(|db| {
        let mut en_cuerpo = texto("Un artículo larguísimo que en algún párrafo menciona las mareas de pasada.");
        en_cuerpo.title = Some("Notas sueltas".into());
        ingest::ingerir(db, &en_cuerpo);
        let mut en_titulo = texto("Apuntes de la playa.");
        en_titulo.title = Some("Mareas".into());
        ingest::ingerir(db, &en_titulo);
        let r = search::buscar(db, "mareas", 10).unwrap();
        assert_eq!(r.len(), 2);
        assert_eq!(r[0].title, "Mareas", "{:?}", r.iter().map(|f| f.title.clone()).collect::<Vec<_>>());
    });
}

//  «pan» encontraba primero «captura-pantalla.png» y después «pan casero»: el
//  prefijo, que es para lo que aún se está escribiendo, valía lo mismo que la
//  palabra entera.
#[test]
fn la_palabra_entera_va_antes_que_lo_que_empieza_igual() {
    banco(|db| {
        let mut a = texto("una imagen");
        a.title = Some("captura-pantalla.png".into());
        ingest::ingerir(db, &a);
        let mut b = texto("una receta");
        b.title = Some("Cómo hacer pan casero sin amasar".into());
        ingest::ingerir(db, &b);
        let r = search::buscar(db, "pan", 10).unwrap();
        assert_eq!(r.len(), 2, "el prefijo sigue encontrando las dos");
        assert!(r[0].title.contains("pan casero"), "{:?}", r.iter().map(|f| f.title.clone()).collect::<Vec<_>>());
        //  Y media palabra mientras se escribe sigue valiendo.
        assert_eq!(search::buscar(db, "amas", 10).unwrap().len(), 1);
    });
}

//  «el vídeo de youtube» no encontraba ningún vídeo de YouTube: de qué sitio es
//  un enlace no estaba en el índice.
#[test]
fn un_enlace_se_encuentra_por_su_sitio() {
    banco(|db| {
        let mut a = url("https://www.youtube.com/watch?v=abc123");
        a.title = Some("Cómo hacer pan casero".into());
        ingest::ingerir(db, &a);
        let mut b = url("https://youtu.be/xyz789");
        b.title = Some("Otro vídeo".into());
        ingest::ingerir(db, &b);
        let mut c = url("https://es.wikipedia.org/wiki/Marea");
        c.title = Some("Marea".into());
        ingest::ingerir(db, &c);
        assert_eq!(search::buscar(db, "youtube", 10).unwrap().len(), 2);
        assert_eq!(search::buscar(db, "pan youtube", 10).unwrap().len(), 1);
        assert_eq!(search::buscar(db, "wikipedia", 10).unwrap().len(), 1);
        assert_eq!(search::buscar(db, "wiki", 10).unwrap().len(), 1);
    });
}

//  La biblioteca de alguien que ya la usa está en la 5, con el índice sin el
//  sitio. Al abrirla con este worker se rehace, y sus enlaces de antes se
//  encuentran por dónde están sin volver a guardarlos.
#[test]
fn una_biblioteca_de_la_5_aprende_a_buscar_por_sitio() {
    let _g = CERROJO.lock().unwrap_or_else(|e| e.into_inner());
    let mut b = [0u8; 8];
    util::azar(&mut b);
    let dir = std::env::temp_dir().join(format!("deriva-v5-{}", util::hex(&b)));
    std::env::set_var("MAREA_DERIVA_DIR", &dir);
    {
        let vieja = db::abrir().expect("no abre");
        let mut p = url("https://www.youtube.com/watch?v=abc123");
        p.title = Some("Pan casero".into());
        ingest::ingerir(&vieja, &p);
        vieja
            .execute_batch(
                "DROP TABLE captures_fts;
                 CREATE VIRTUAL TABLE captures_fts USING fts5(
                     capture_id UNINDEXED,
                     title, author, excerpt, summary, note, content_text, tags,
                     tokenize = \"unicode61 remove_diacritics 2\"
                 );
                 INSERT INTO captures_fts (capture_id, title, author, excerpt, summary, note, content_text, tags)
                   SELECT id, title, author, excerpt, summary, note, content_text, '' FROM captures;
                 PRAGMA user_version = 5;",
            )
            .expect("no la puedo dejar como estaba");
    }
    let db = db::abrir().expect("no abre la de la 5");
    let v: i64 = db.query_row("PRAGMA user_version", [], |r| r.get(0)).unwrap();
    assert_eq!(v, db::VERSION);
    assert_eq!(search::buscar(&db, "pan", 10).unwrap().len(), 1, "lo de antes se sigue encontrando");
    assert_eq!(search::buscar(&db, "youtube", 10).unwrap().len(), 1, "y ahora también por su sitio");
    drop(db);
    let _ = std::fs::remove_dir_all(&dir);
    std::env::remove_var("MAREA_DERIVA_DIR");
}
