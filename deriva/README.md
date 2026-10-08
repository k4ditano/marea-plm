# deriva-worker

La biblioteca local de Deriva: guarda lo que le sueltas a Marea, lo busca y lo
devuelve.

Es un binario aparte y no código QML por una razón concreta: Quickshell recarga
el shell entero cuando se guarda un fichero del repo, y una base de datos a
medio escribir no sobrevive a eso. Aquí abajo, una recarga de la interfaz no
toca nada.

## Usarlo

```sh
./marea deriva where            # dónde está cada cosa
./marea deriva stats            # cuántas cosas hay
./marea deriva search --query "pulpo"
./marea deriva integrity-check --deep
./marea deriva backup --keep 5
./marea deriva export --directory /ruta/absoluta
```

Se compila solo la primera vez que se le llama. A mano:

```sh
cd deriva && cargo build --release
```

`MAREA_DERIVA_DIR` mueve la biblioteca entera y `MAREA_DERIVA_SOCKET` el socket.
Las pruebas los usan para no acercarse a la del usuario.

## Cómo habla

Marea le habla por un socket Unix privado en `$XDG_RUNTIME_DIR/proyecto-marea/`,
con permisos `0600`. JSON Lines versionado, una línea por mensaje:

```json
{"v":1,"id":"req-42","method":"search","params":{"query":"liquid UI","limit":20}}
{"v":1,"id":"req-42","ok":true,"result":{"items":[]}}
```

Nada de puertos, ni siquiera en `localhost`: un puerto lo alcanza cualquier
proceso de la máquina, incluida cualquier pestaña con un `fetch`.

Métodos: `ping`, `ingest`, `search`, `list`, `get`, `stats`, `integrity_check`,
`repair_index`, `backup`, `export`, `trash`, `untrash`, `shutdown`. La línea de
órdenes usa **el mismo despachador**: dos caminos hacia la misma base es como se
acaba teniendo dos comportamientos y una prueba que cubre uno.

Marea (pleamar) has no socket of her own, so she uses the same protocol two
other ways:

- `deriva-worker call <method> --params '<json>'` runs any method once
  (`home` with a filter, `annotate`, `trash`, `enrich`…). `--preview-file
  <path>` reads a cover from disk and hands it to `enrich` as its
  `preview_b64`.
- `deriva-worker stdio` reads a request per line on its input and answers a
  line each on its output, with the library open and the search model loaded
  once. She keeps one alive while you search (from the command line each
  search loads the model again, about three seconds) and closes its input two
  minutes after the last search.

## Lo que no hace

- **No sale a la red.** Ni una conexión, y no la va a abrir. Sí hay
  enriquecimiento de URLs —el título, el autor y la portada de un enlace—, pero
  quien sale es la casa: `tools/web`, con sus reglas anti-SSRF, y lo que trae
  entra por el método `enrich`. Aquí no hay nada que proteger porque no hay nada
  que salga, y eso es fácil de comprobar y fácil de perder.
- **No ejecuta nada.** No lanza procesos ni interpreta lo guardado.
- **No borra lo que no le pidan por su nombre.** Tirar a la basura y destruir
  son cosas distintas; `trash` marca, y la fila sigue ahí.
- **No acepta rutas libres** salvo en `export`, donde la ruta la elige el
  usuario y la valida el controlador antes de llegar aquí.

## De qué sitio viene cada cosa

De la URL sola, sin pedirle nada a nadie: `adaptadores.rs` reconoce YouTube,
Reddit, X, GitHub, Vimeo, Twitch, y por extensión los PDF, las imágenes, los
vídeos y el audio. De ahí salen tres cosas:

- **El sitio** (`source`), que la interfaz enseña con su marca y su color.
- **El tipo de verdad**: un enlace de YouTube es un `video` aunque no acabe en
  `.mp4`.
- **Una canónica propia de ese sitio**, que es lo que hace que `youtu.be/ID`,
  `watch?v=ID`, `watch?v=ID&t=90`, `&list=…` y `shorts/ID` sean **el mismo
  vídeo**. Sin eso, arrastrar el mismo vídeo desde dos sitios guarda dos
  capturas y «esto ya lo tenías» no se cumple nunca.

Y lo que no se sabe no se inventa: un canal de YouTube no finge ser un vídeo
—sin identificador con la forma correcta no hay canónica—, y una página
cualquiera se queda con su dominio de título, que dice más que «Sin título».

Lo que hace falta la red —el título de verdad, el canal, la miniatura— llega
por `enrich`, y lo trae quien tiene red. Ver
[PRIVACIDAD.md](../design/deriva/PRIVACIDAD.md).

## Carpetas y resúmenes

Las tres carpetas de fábrica —Proyectos, Leer luego, Inspiración— son un
ejemplo, no la lista. `space_put` y `space_delete` hacen las tuyas: se crean
vacías, se renombran sin cambiar de id, y al quitarlas **lo de dentro se
queda**. El id sale del nombre y es un id: `Investigación` → `investigacion`.

Y `classify` guarda lo que la IA entienda de una captura: un resumen, unas
etiquetas y, si encaja, una carpeta. Aquí no hay modelo ninguno —igual que no
hay red—: eso lo pide la casa con el motor del usuario y entra ya escrito. Las
reglas de qué se pisa son más estrictas que las de `enrich`, porque un título
que trae una página es un hecho y esto es la opinión de un modelo:

- La **nota** no se toca nunca: es tuya.
- El **resumen**, solo si no había.
- Las **etiquetas se suman**; las tuyas se quedan donde estaban.
- Y la **carpeta**, solo si la captura no estaba en ninguna.

El resumen vive en su propia columna y **entra en el índice**, con casi el peso
de una etiqueta: son cuarenta palabras elegidas para decir de qué va esto, así
que una coincidencia ahí vale mucho más que una en medio del artículo. Un
resumen que no se encuentra buscando no le sirve a nadie.

## Sabe de lo que hay dentro

`enrich` guarda también el **cuerpo**: el texto de la página que enlazaste y el
que se saque de un fichero. Va a `content_text`, que ya estaba en el índice y
estaba vacío para todo lo que no fuera una selección de texto. Sin eso, buscar
una frase de un artículo que guardaste no encontraba nada y la biblioteca solo
sabía de títulos.

Se escribe **una vez y se queda**. La captura es una copia de lo que viste; una
que se relee sola dentro de un mes ya no lo es.

Y lo saca la casa, no este worker: leer una página es salir a la red y sacar
texto de un PDF es lanzar un proceso sobre un fichero que te ha dado otro. Aquí
entra ya leído.

## Y busca por significado, si le pones el modelo

`search` devuelve primero lo que CONTIENE tus palabras —FTS5 con BM25, todas y
luego cualquiera— y rellena por detrás con lo que se PARECE. Lo segundo solo si
hay modelo en `<base>/modelo`, y si no lo hay todo funciona como antes.

El crate se compila con `local-only`: este worker no puede descargar un modelo
igual que no puede abrir una conexión. Lo pone ahí la casa.

Los vectores viven en `capture_vectors`, crudos y con su medida al lado. Tabla
aparte porque el día que haya un modelo mejor se vacía y se rehace sin tocar ni
una captura, y la medida porque comparar vectores de modelos distintos no da un
error: da un parecido inventado.

Y `similar` enseña el parecido con su número, que es la única manera de calibrar
el umbral sin adivinar.

## Dónde vive lo guardado

```text
${XDG_DATA_HOME:-~/.local/share}/proyecto-marea/deriva/
├── library.sqlite3
├── blobs/ab/cd/<sha256>
├── previews/
├── exports/
└── backups/
```

El nombre de un blob es su hash. Eso trae tres cosas gratis: el mismo fichero
guardado dos veces ocupa una, comprobar la integridad es volver a hashear, y no
hay que escapar nombres que vienen del usuario —que es de donde salen la mitad
de los agujeros de un almacén de ficheros—.

## Dos reglas que sostienen el resto

**El blob antes que la fila.** Un corte entre los dos deja, como mucho, bytes
sin dueño en el disco: se ven, se cuentan y se barren. Al revés dejaría una
captura visible apuntando a un fichero que no existe, y eso ya no se puede
reparar leyendo la base.

**Nada se da por guardado hasta que SQLite confirma.** La animación de éxito de
Marea espera a esta confirmación, no al revés.

## Probarlo

```sh
./test-prototype --deriva
```

Por dentro con `cargo test` —la base y los blobs a mano— y por fuera con Node,
que es donde se comprueba que el binario y el socket hacen lo que dicen. La
prueba que da nombre a la fase abre y cierra procesos distintos sobre el mismo
disco: si algo viviera en memoria, se caería ahí.

## Instalarlo y retirarlo

```sh
./marea deriva instalar      # worker, plugin y accesorios; NACE APAGADO
./marea deriva desinstalar   # se lo lleva todo menos tu biblioteca
```

Nace apagado a propósito: el plugin aparece en Ajustes → Plugins con lo que
implica encenderlo a la vista, y hasta que no le des al interruptor no corre, no
guarda y no recibe nada.

Y al retirarlo no queda nada salvo la biblioteca, que es tuya. El desinstalador
dice dónde está y cómo llevártela o borrarla; exportar y borrar son operaciones
explícitas y separadas, y ninguna pasa por accidente.

## Traerte lo que ya tenías

```sh
./marea deriva import --folder ~/Documentos/recortes
./marea deriva import --bookmarks ~/Descargas/bookmarks.html --space leer-luego
./marea deriva import --deriva /donde/exportaste
```

La tercera es la vuelta de `export`, y existe porque una exportación que no se
puede reimportar es un archivo muerto con formato bonito.

Ninguna se ejecuta sola, ninguna vigila una carpeta y ninguna sale a la red. La
ruta la eliges tú.

## Cuando algo no va

```sh
./marea deriva doctor
```

Contesta la primera pregunta de cualquier diagnóstico: qué versión de qué está
hablando con qué. Versión del binario, esquema esperado y real, dónde está todo,
cuántas copias hay y si la biblioteca está entera.

Los permisos, la privacidad y cómo llevarte tus cosas están en
[`design/deriva/PRIVACIDAD.md`](../design/deriva/PRIVACIDAD.md).

## Windows (MSVC)

From the Marea checkout in PowerShell:

```powershell
cargo build --release --locked --manifest-path deriva/Cargo.toml
cargo test --locked --manifest-path deriva/Cargo.toml
python windows/test-deriva-native.py --worker deriva/target/release/deriva-worker.exe
.\deriva\target\release\deriva-worker.exe where
```

SQLite is bundled. Marea's Windows installer packages this executable and uses
the same JSON CLI dispatcher. Data defaults to
`%LOCALAPPDATA%/proyecto-marea/deriva`; `MAREA_DERIVA_DIR` overrides it. Paths with
spaces and Unicode are supported. The default directory inherits the profile's
ACL; custom directories inherit their parent's ACL. The worker uses the OS
random source for IDs and temporary names on both platforms.

The Unix socket `serve` command is unavailable on Windows and fails explicitly;
`where` reports `socket: null`. CLI ingestion, FTS search, backup and export/import
do not need the server, a shell, WSL or an external SQLite installation. Semantic
search is optional, requires separately supplied local model files and has not
been validated with those files on Windows. The worker makes no network request.
