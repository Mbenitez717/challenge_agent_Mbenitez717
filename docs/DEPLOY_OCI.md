# Despliegue paso a paso en OCI Compute

Esta guía presupone que la aplicación ya funciona localmente. Utiliza una instancia
Linux con Docker porque es una ruta fácil de entender, reproducible y suficiente
para el prototipo.

Documentación oficial de referencia:

- [Crear una instancia de Compute](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/launchinginstance.htm)
- [Conectarse a una instancia Linux](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/connect-to-linux-instance.htm)
- [Instalar Docker Engine en Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [Enviar imágenes a OCI Container Registry](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrypushingimagesusingthedockercli.htm)

## A. Preparar Git sin revelar información

Desde la computadora local:

```powershell
git init
git add .
git status
git commit -m "Prototipo inicial del asistente RAG"
git branch -M main
git remote add origin https://github.com/USUARIO/REPOSITORIO.git
git push -u origin main
```

Revise `git status` antes del commit. **No deben aparecer** `.env`, los PDF ni
`data/index_*`. El repositorio puede ser privado.

## B. Crear la red y la instancia

1. Ingrese a la consola de OCI.
2. Cree o seleccione un compartimento.
3. En **Networking > Virtual Cloud Networks**, use **Start VCN Wizard > Create VCN
   with Internet Connectivity**. Esto crea red pública, gateway de internet y rutas.
4. En **Compute > Instances**, pulse **Create instance**.
5. Nombre sugerido: `santos-pegasus-rag`.
6. Imagen: Ubuntu 22.04 o 24.04.
7. Si dispone de Ampere A1, use preferentemente 2 OCPU y 12 GB de RAM para Gemma 3
   4B. El prototipo verificado también funciona en `VM.Standard.E2.1.Micro`, pero por
   su límite aproximado de 1 GB de RAM debe usar `qwen2.5:0.5b` y swap.
8. Seleccione la subred pública y asigne una IP pública.
9. Genere o cargue una clave SSH y guarde la clave privada en un lugar seguro. OCI no
   podrá volver a mostrar una clave privada generada.
10. Cree la instancia y anote su IP pública.

## C. Configurar reglas de red

En el Network Security Group (recomendado) o la Security List de la subred, agregue
reglas de entrada **stateful**:

| Origen | Protocolo | Puerto destino | Uso |
|---|---|---:|---|
| Su IP pública `/32` | TCP | 22 | Administración SSH |
| `0.0.0.0/0` | TCP | 8501 | Acceso web temporal al prototipo |

No abra SSH a todo Internet si puede restringirlo a su dirección. Cuando configure
Nginx/HTTPS, abra 80 y 443 y cierre 8501 al público.

## D. Conectarse por SSH

En PowerShell, desde la carpeta donde guardó la clave:

```powershell
ssh -i .\clave-oci.key ubuntu@IP_PUBLICA
```

Si eligió Oracle Linux en lugar de Ubuntu, el usuario habitual es `opc`.

## E. Instalar Docker y Git

En la instancia Ubuntu:

```bash
sudo apt update
sudo apt install -y git docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
exit
```

Vuelva a conectarse por SSH para que se aplique el grupo. Compruebe:

```bash
docker --version
docker compose version
```

Si su versión de Ubuntu no ofrece `docker-compose-v2`, use el procedimiento oficial
de instalación de Docker enlazado al inicio de esta guía.

### Configuración usada en la instancia E2.1.Micro

El despliegue probado el 21 de julio de 2026 utilizó Ubuntu 24.04.4 LTS, Docker
29.1.3, Docker Compose 2.40.3 y un archivo swap persistente de 8 GB. Para crear el
swap una sola vez:

```bash
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

Antes de añadir la línea, compruebe con `grep /swapfile /etc/fstab` que no exista
para evitar duplicados.

## F. Descargar el proyecto

```bash
git clone https://github.com/USUARIO/REPOSITORIO.git santos-pegasus-rag
cd santos-pegasus-rag
mkdir -p data
```

Para un repositorio privado, use un token de acceso personal o una clave SSH de
despliegue. No escriba el token dentro del código.

## G. Copiar los PDF de forma privada

Desde una nueva ventana de PowerShell en la computadora local:

```powershell
scp -i .\clave-oci.key .\data\Manual_Onboarding.pdf ubuntu@IP_PUBLICA:/home/ubuntu/santos-pegasus-rag/data/
scp -i .\clave-oci.key .\data\Manual_de_Respuestas_Incidentes.pdf ubuntu@IP_PUBLICA:/home/ubuntu/santos-pegasus-rag/data/
```

Los documentos no pasan por GitHub. En el servidor, confirme:

```bash
ls -lh data/*.pdf
```

## H. Crear la configuración local sin secretos

En la instancia:

```bash
cp .env.example .env
nano .env
```

Configure como mínimo:

```dotenv
RAG_PROVIDER=ollama
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_CHAT_MODEL=qwen2.5:0.5b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
RAG_TOP_K=1
```

Guarde con `Ctrl+O`, Enter y salga con `Ctrl+X`.

## I. Construir y arrancar

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=100
```

Valide desde la instancia:

```bash
curl http://localhost:8501/_stcore/health
```

Debe responder `ok`. Si Ubuntu tiene UFW activo:

```bash
sudo ufw allow 8501/tcp
sudo ufw status
```

Abra desde su computadora:

```text
http://IP_PUBLICA:8501
```

La aplicación descarga los modelos que falten e indexa los documentos durante el
arranque del contenedor. En la instancia de 1 GB conviene cargar un índice generado
previamente para evitar presión de memoria durante la primera fragmentación. Cuando la
URL está disponible, el chat ya está listo para usar.

El despliegue verificado quedó disponible en
[http://163.176.222.158:8501/](http://163.176.222.158:8501/) y el health check
`http://163.176.222.158:8501/_stcore/health` respondió `ok`.

## J. Actualizar la aplicación

```bash
cd ~/santos-pegasus-rag
git pull
docker compose up -d --build
docker image prune -f
```

Para ver problemas:

```bash
docker compose logs -f
```

## K. Evidencia requerida

1. Abra la URL pública y confirme que indique **Base de conocimiento disponible**.
2. Realice al menos dos preguntas: una documental y otra fuera de tema.
3. Confirme que la interfaz no solicite archivos ni acciones de indexación.
4. Tome una captura donde se vea la aplicación y la dirección pública del navegador.
5. Guarde las capturas en `docs/evidencias/` con nombres descriptivos.
6. Complete `docs/EVIDENCIA_OCI.md` y haga commit de la evidencia, siempre que no
   muestre contenido confidencial.

## L. Recomendaciones antes de producción

- Use un dominio, Nginx y certificado TLS; exponga 443, no 8501.
- Añada autenticación o limite el origen mediante NSG/VPN.
- Use cuotas y alertas de presupuesto para evitar recursos fuera de Always Free.
- Configure copias de seguridad para `data/` y monitoreo/logs.
- Restrinja IAM por mínimo privilegio y mantenga el sistema actualizado.
- Considere OCI Container Registry y un pipeline CI/CD cuando el prototipo se
  estabilice.
