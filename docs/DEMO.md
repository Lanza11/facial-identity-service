# Guion de la demo

Duración estimada: 10–15 minutos. Todo corre en local.

## Antes de la reunión (una sola vez)

```powershell
docker compose up -d                       # la primera vez descarga ~4 GB de imágenes
python scripts/bootstrap_compreface.py     # crea app + servicio en CompreFace y escribe .env
docker compose up -d facade                # recrea la fachada con la API key nueva
```

Comprueba que todo está arriba:

- <http://localhost:8080/health> debe responder `{"status":"UP","engine":"compreface","engineStatus":"UP"}`.
- <http://localhost:8080/demo/> muestra la página de demo, con la API key `demo-key` ya cargada.

> Usa solo rostros de compañeros que acepten participar. No uses datos de clientes reales.

## Durante la reunión

1. **Contexto (1 min).** El servicio es independiente: lo puede consumir la app móvil, el web administrativo o nada, según lo que se decida. La página de demo hace el papel de ese consumidor.
2. **Registrar.** En la pestaña *Registrar*, crea "Ana" (`CUST-1001`). Enciende la cámara, captura y registra. Repite con una segunda persona.
   - Muestra una regla de negocio: tapa la cara o captura sin nadie y aparece `NO_FACE`. Con dos personas en cuadro aparece `MULTIPLE_FACES`.
3. **Verificar 1:1.** En la pestaña *Verificar*, elige "Ana":
   - Ana frente a la cámara da **Coincide**, con una similitud alrededor del 99%.
   - La otra persona frente a la cámara da **No coincide**.
4. **Identificar 1:N.** En la pestaña *Identificar*, cualquiera de las dos personas es reconocida sin decir quién es. Alguien no registrado da "Ninguna persona registrada coincide".
5. **Desactivar.** En *Administrar*, desactiva a Ana. Verificarla da `SUBJECT_INACTIVE` y ya no aparece al identificar. Reactívala.
6. **Bloqueo.** Verifica varias veces a Ana con la otra persona. Tras 5 fallos, Ana queda **bloqueada** temporalmente (`SUBJECT_LOCKED`).
7. **Auditoría.** En la pestaña *Auditoría* se ve cada operación con su resultado y el hash de la imagen. Las fotos no se guardan.
8. **Eliminar.** En *Administrar*, elimina a una persona. En la UI de CompreFace (<http://localhost:8000>, usuario `demo@fis.local` / `Demo12345!`) se ve que el sujeto desapareció también del motor. Señala que el motor solo conoce UUIDs, nunca nombres ni cédulas.
9. **Contrato.** Abre Swagger (<http://localhost:8080/docs>): ningún campo expone CompreFace. Así es como la app Flutter consumiría el servicio (problem+json con `slug`, igual que hoy).
10. **Cambiar de motor.** Pon `FIS_ENGINE=fake` en `.env` y ejecuta `docker compose up -d facade`. El badge pasa a `motor: fake`: misma API, mismas reglas y misma auditoría con otro motor. El motor simulado solo reconoce archivos idénticos, así que conviene hacerlo subiendo el mismo archivo. Vuelve a `FIS_ENGINE=compreface` al terminar.
11. **Cierre: siguientes pasos.**
    - Liveness (anti‑spoofing).
    - Revisión legal y de licencias.
    - Benchmark de modelos open source (YuNet + SFace) con fotos reales.
    - Decidir el caso de uso y el consumidor (app o web administrativo).
    - Despliegue cloud‑agnóstico (contenedor + PostgreSQL/pgvector).

    Ver [ANALISIS.md](ANALISIS.md).

## Reiniciar la demo

- Para borrar solo los datos de la fachada (personas y auditoría):

  ```powershell
  docker compose rm -sf facade; docker volume rm facial-identity_fis-data; docker compose up -d facade
  ```

  Ojo: los rostros siguen en CompreFace hasta que se eliminen.
- Para borrar todo, incluido CompreFace (después hay que volver a ejecutar el bootstrap):

  ```powershell
  docker compose down -v
  ```

## Si algo falla

| Síntoma | Causa probable |
|---|---|
| `engineStatus: DOWN` | CompreFace aún está arrancando (tarda ~1 minuto) o falta `COMPREFACE_API_KEY` en `.env` |
| La cámara no enciende | El navegador solo permite la cámara en `localhost` o HTTPS. Usa <http://localhost:8080/demo/> |
| `UNAUTHORIZED` | La API key de la página no coincide con `FIS_API_KEY` |
