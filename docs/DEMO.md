# Guion de la demo

Hay dos públicos y por eso dos partes:
- **Parte 1, para gerencia** (10 minutos): cuatro escenarios del negocio, sin nada técnico a la vista.
- **Parte 2, para desarrolladores** (opcional, 5–10 minutos): se activa el *Modo técnico*.

Todo corre en local.

## Antes de la reunión

Una sola vez:

```powershell
docker compose up -d                       # la primera vez descarga ~4 GB de imágenes
python scripts/bootstrap_compreface.py     # crea app + servicio en CompreFace y escribe .env
docker compose up -d --build facade        # recrea la fachada (incluye MediaPipe para la prueba de vida)
```

El mismo día de la demo:

- <http://localhost:8080/health> debe responder `{"status":"UP","engine":"compreface","engineStatus":"UP"}`.
- Abre <http://localhost:8080/demo/> en el navegador de la presentación y **autoriza la cámara** una vez, antes de empezar.
- Deja el interruptor **Modo técnico apagado**.
- Ten a mano **una foto impresa o en otro celular** de la persona que vas a registrar. Es para el escenario 4.
- Busca un lugar con buena luz de frente. Evita tener una ventana detrás.
- Ensaya una vez la prueba de vida: parpadear y girar la cabeza hacia el lado que pida, con un movimiento claro.

> Usa solo rostros de compañeros que acepten participar. No uses datos de clientes reales.

## Parte 1: escenarios (gerencia)

La columna **"Qué está pasando"** de cada escenario ya narra cada paso; puedes leerla en voz alta.

1. **Portada (30 s).** "Registramos el rostro del cliente una sola vez y, desde ahí, sabemos en segundos si quien está al otro lado es el titular." Señala la nota de privacidad: no se guardan fotos.
2. **Nuevo cliente.**
   - Crea a un compañero ("Ana Pérez", `CL-1001`).
   - Muestra el paso de **autorización**: sin ella el sistema no deja registrar el rostro (Ley 1581).
   - En la cámara, la guía dice qué hacer: centrarse, parpadear, girar la cabeza y volver al frente. La foto se toma sola.
3. **¿Es realmente el titular?**
   - En el celular simulado, Ana va a **pagar su cuota**. Antes, la app le pide confirmar que es ella.
   - Resultado: su foto registrada al lado de la de ahora, con el porcentaje de similitud y "¡Eres tú, Ana!".
   - Repite con **otra persona** frente a la cámara: "No pudimos confirmar que eres Ana", y el pago no sigue.
4. **¿Quién es este cliente?** Llega alguien sin documento; el asesor pulsa *Empezar* y el sistema lo reconoce entre todos los clientes. Una persona no registrada da "No encontramos a esta persona".
5. **¿Y si intentan engañarlo con una foto?** (cierre)
   - Elige a Ana y pulsa *Pagar cuota*. Pon **la foto de Ana** frente a la cámara.
   - La foto no parpadea, así que tras unos segundos aparece **"No detectamos a una persona real"**.
   - Justo debajo: *"Sin prueba de vida, la foto habría pasado: el reconocimiento por sí solo habría dicho que es Ana (≈99%)"*. Es el argumento de por qué la prueba de vida es indispensable.
6. **Cierre.** Es un módulo interno e independiente: puede usarlo la app de clientes, el web administrativo o ambos.

## Parte 2: modo técnico (desarrolladores)

Activa el interruptor **Modo técnico** (arriba a la derecha). Aparecen:
- Swagger.
- El estado del motor.
- La API key.
- Sobre la cámara, los valores en vivo de la prueba de vida: parpadeo, giro, tamaño y centro del rostro.
- La opción de subir una foto en lugar de usar la cámara.
- El panel **"Llamadas al servicio"**, con cada petición y su JSON.

1. **Personas.** Desactiva a Ana: verificarla da *"Este cliente está desactivado"* y deja de aparecer al identificar. Reactívala.
2. **Bloqueo.** Verifica a Ana varias veces con otra persona. Tras 5 fallos queda **bloqueada** unos minutos.
3. **Auditoría.** Cada operación con su resultado, la prueba de vida (superada, fallida o sin prueba) y la huella SHA‑256 de la imagen. Las fotos no se guardan.
4. **Eliminar.** En *Personas*, elimina a alguien. En la UI de CompreFace (<http://localhost:8000>, `demo@fis.local` / `Demo12345!`) se ve que también desapareció del motor, que solo conoce UUIDs.
5. **Contrato.** Swagger (<http://localhost:8080/docs>): ningún campo expone CompreFace. Errores problem+json con `slug`, como ya consume la app Flutter.
6. **Cambiar de motor.** `FIS_ENGINE=fake` en `.env` y luego `docker compose up -d facade`: misma API, mismas reglas, otro motor. El motor simulado solo reconoce archivos idénticos, así que conviene usarlo subiendo fotos. Vuelve a `compreface` al terminar.
7. **Siguientes pasos:**
   - Prueba de vida también del lado del servidor.
   - Revisión legal y de licencias de los modelos.
   - Benchmark con fotos reales (YuNet + SFace).
   - Decidir el consumidor (app o web administrativo).
   - Despliegue cloud‑agnóstico.

   Ver [ANALISIS.md](ANALISIS.md).

## Reiniciar la demo

- Para borrar solo los datos de la fachada (personas, autorizaciones y auditoría):

  ```powershell
  docker compose rm -sf facade; docker volume rm facial-identity_fis-data; docker compose up -d facade
  ```

  Ojo: los rostros siguen en CompreFace hasta que se eliminen. Lo más limpio es eliminar a las personas desde *Personas* antes de reiniciar.
- Para borrar todo, incluido CompreFace (después hay que volver a ejecutar el bootstrap):

  ```powershell
  docker compose down -v
  ```

## Si algo falla

| Síntoma | Causa probable |
|---|---|
| `engineStatus: DOWN` | CompreFace aún está arrancando (tarda ~1 minuto) o falta `COMPREFACE_API_KEY` en `.env` |
| La cámara no enciende | El navegador solo permite la cámara en `localhost` o HTTPS. Usa <http://localhost:8080/demo/> y revisa el permiso de cámara del sitio |
| "No pudimos preparar la cámara" | No cargó MediaPipe: reconstruye la fachada (`docker compose up -d --build facade`) o, fuera de Docker, ejecuta `scripts/fetch_mediapipe.py` |
| No detecta el giro | Gira con más decisión. En modo técnico, el valor `giro` debe pasar de ±0,17. Si al girar a la derecha sale "Hacia el otro lado", cambia `USER_RIGHT_SIGN` en `demo/liveness.js` |
| Se queda en "Acércate un poco" | La cara debe ocupar al menos un tercio del ancho. Acércate, o baja `MIN_FACE_WIDTH` en `demo/liveness.js` |
| "Foto no disponible en este equipo" | Las miniaturas de la comparación viven en el navegador donde se registró la persona. Registra en el mismo navegador de la demo |
| "Falta la autorización" | La persona se creó antes de que existiera el paso de autorización. Regístrala de nuevo desde *Nuevo cliente* |
| `UNAUTHORIZED` | La API key del modo técnico no coincide con `FIS_API_KEY` |
| La página se ve como la versión anterior | Recarga con Ctrl+F5 |
