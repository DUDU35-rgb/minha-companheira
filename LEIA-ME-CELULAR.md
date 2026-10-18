# Minha Companheira Virtual IA — Publicar SÓ pelo celular

Esta versão foi montada com **pouquíssimos arquivos** justamente para você
conseguir subir tudo pelo navegador do celular, sem computador.

Arquivos desta pasta:
- `main.py` — o aplicativo inteiro (servidor + IA + banco de dados)
- `index.html` — a telinha do app (já com todo o visual e os botões embutidos)
- `requirements.txt` — a lista do que o servidor precisa instalar
- `Dockerfile` e `render.yaml` — receitas para o Render publicar sozinho

---

## PASSO 1 — Criar o repositório no GitHub (pelo celular)
1. Abra o navegador e entre em **github.com** (crie uma conta grátis se não tiver).
2. Toque em **+** (canto superior) → **New repository**.
3. Dê um nome, ex.: `minha-companheira`. Deixe **Public**. Toque em **Create repository**.

## PASSO 2 — Enviar os arquivos
1. Na página do repositório novo, toque em **Add file** → **Upload files**.
2. Toque em **choose your files** e selecione os arquivos que te entreguei
   (descompacte o .zip no celular primeiro — veja a dica no fim).
3. Suba **todos** eles: `main.py`, `index.html`, `requirements.txt`,
   `Dockerfile`, `render.yaml`.
4. Role para baixo e toque em **Commit changes**.

## PASSO 3 — Publicar no Render (ganha o link clicável)
1. Abra **render.com** e toque em **Get Started** → entre com sua conta do GitHub.
2. No painel, toque em **New +** → **Web Service**.
3. Escolha o repositório `minha-companheira` que você acabou de criar.
4. O Render vai detectar o `Dockerfile` sozinho. Plano: **Free**.
5. Toque em **Create Web Service** e espere alguns minutos (a 1ª vez demora).
6. Quando aparecer **Live**, você verá um link no topo, algo como
   `https://minha-companheira.onrender.com` — **esse é o seu app!** 🎉

## PASSO 4 — Ligar as inteligências (opcional, para funcionar de verdade)
Sem chaves, o app abre e você navega, mas a conversa/voz/vídeo ficam
"desligados". Para ligar:
1. No Render, abra seu serviço → aba **Environment**.
2. Preencha os valores:
   - `PUBLIC_BASE_URL` = o link que o Render te deu (ex.: `https://minha-companheira.onrender.com`)
   - `LLM_API_KEY` = sua chave da OpenAI (conversa)
   - `TTS_API_KEY` = sua chave da OpenAI (voz) — pode ser a mesma
   - (Vídeo com lip-sync é opcional e exige um provedor de vídeo próprio;
     preencha `VIDEO_*` e `LIPSYNC_*` só se tiver um.)
3. Salve. O Render reinicia sozinho e pronto.

> Segurança: as chaves ficam **só no servidor** (no Render), nunca dentro do app
> no celular. Os vídeos saem marcados como "gerado por IA" e a foto exige o seu
> consentimento. Isso é de propósito.

---

## Dica — abrir o .zip no celular
- **Android:** use o app **Files/Arquivos** ou **Google Files** → toque no .zip → **Extrair**.
- **iPhone:** salve o .zip no app **Arquivos** → toque nele → ele cria uma pasta.
- Depois é só escolher esses arquivos no passo "Upload files" do GitHub.

Se travar em qualquer passo, me diga em qual número você está que eu te ajudo. 💜
