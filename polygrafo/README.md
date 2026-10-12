# Polígrafo pessoal

Aplicação local (web + linha de comandos) para verificar afirmações publicadas no
Facebook, Instagram, TikTok, X/Twitter, YouTube e outras redes sociais. Para cada
publicação, a aplicação:

1. **Extrai o conteúdo** a partir do link, de texto colado ou de uma captura de ecrã.
2. **Identifica as afirmações verificáveis** e separa-as de opiniões, previsões e sátira.
3. **Pesquisa fontes** na web, a favor e contra, incluindo fact-checks profissionais já publicados.
4. **Avalia as fontes** (fiabilidade do domínio × relevância para a afirmação).
5. **Calcula um score de 0 a 100** por afirmação e um score global, com as provas e as ligações.

## Arquitetura

```
link / texto / imagem
        │
        ▼
 ingest.py ──── yt-dlp (TikTok, Instagram, Facebook, X, YouTube…)
        │       └─ alternativa: metadados Open Graph do HTML público
        ▼
 analyzer.extract_claims ── Claude (visão + JSON estruturado)
        │
        ▼  (por afirmação, em paralelo)
 factcheck_db.py ── Google Fact Check Tools API (opcional)
 analyzer.research ── Claude + web_search + web_fetch (pesquisa a favor e contra)
 analyzer.assess ── Claude (JSON estruturado: apoia / refuta / neutro + relevância)
        │           └─ descarta URLs que não apareceram na pesquisa real
        ▼
 sources.py ── fiabilidade por domínio (lista editável)
 scoring.py ── score determinístico, calculado em código
        │
        ▼
 Relatório (web, terminal ou JSON)
```

## Instalação

Requer Python 3.10 ou superior.

```bash
cd polygrafo
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # e preencha ANTHROPIC_API_KEY
```

- `ANTHROPIC_API_KEY` (obrigatória): chave da [Claude API](https://console.anthropic.com).
- `GOOGLE_FACTCHECK_API_KEY` (opcional, gratuita): ativa a pesquisa em fact-checks
  profissionais através da [Google Fact Check Tools API](https://developers.google.com/fact-check/tools/api).
- `POLYGRAFO_TRANSCRIBE=1` (opcional): transcreve o áudio de vídeos localmente. Requer
  `pip install faster-whisper` e `ffmpeg`. É útil no TikTok e no Reels, onde a afirmação
  costuma estar na fala e não na legenda.

## Utilização

**Interface web**

```bash
uvicorn polygrafo.main:app --reload
# abra http://127.0.0.1:8000
```

**Linha de comandos**

```bash
python cli.py --url "https://www.tiktok.com/@conta/video/123"
python cli.py --text "Segundo o INE, a inflação em Portugal foi de 10% em 2024"
python cli.py --image captura.png --json
```

**API HTTP**

`POST /api/check` (multipart: `url`, `text`, `image`) devolve o relatório em JSON.
`POST /api/extract` (`url`) só mostra o que foi possível ler da publicação.

## Publicar online (privado, com senha)

A app pode ser alojada no [Render](https://render.com) com o ficheiro `render.yaml`
que está na raiz do repositório. Todas as páginas e pedidos exigem utilizador e senha
(HTTP Basic sobre HTTPS). Se a senha não estiver configurada, a app recusa todos os
pedidos, por isso nunca fica aberta por engano.

**1. Chave da Claude API**
1. Entre em <https://console.anthropic.com> e carregue créditos. A API é paga à parte
   da subscrição do Claude.
2. Em *Settings → Limits*, defina um limite de gastos mensal.
3. Em *API Keys*, crie uma chave e copie-a.

**2. Render**
1. Crie uma conta em <https://render.com> com a opção *GitHub*.
2. Escolha *New → Blueprint* e selecione o repositório `toolsforbuilders`. Use o ramo
   onde está o polígrafo: o `main`, depois do merge do PR.
3. Preencha as variáveis pedidas:
   - `ANTHROPIC_API_KEY`: a chave do passo 1.
   - `POLYGRAFO_PASSWORD`: uma senha com pelo menos 12 caracteres.
   - `GOOGLE_FACTCHECK_API_KEY`: opcional, pode ficar vazia.
4. Confirme e aguarde a instalação, que demora alguns minutos. O Render mostra o
   endereço da app, por exemplo `https://polygrafo-xxxx.onrender.com`.

**3. Usar**
Abra o endereço no browser (também funciona no telemóvel). Quando for pedido, entre
com o utilizador `eu` e a senha que definiu. Pode mudar o utilizador com a variável
`POLYGRAFO_USER`.

**Limitações do plano gratuito do Render:**
- O serviço adormece após 15 minutos sem uso. A primeira visita depois disso demora
  cerca de um minuto a acordar.
- Há 750 horas de instância gratuitas por mês.
- Se o serviço reiniciar ou adormecer a meio de uma análise, essa análise perde-se e
  tem de ser repetida.
- O TikTok e o Instagram bloqueiam com frequência pedidos vindos de servidores. Nesse
  caso, cole o texto da publicação ou envie uma captura de ecrã.

**Segurança:**
- Após 5 senhas erradas, o IP fica bloqueado durante 15 minutos.
- As chaves e a senha ficam guardadas só nas variáveis do Render, nunca no código.
- Se o repositório for público, o código-fonte fica visível para qualquer pessoa, mas
  sem chaves nem senhas.

## Como é calculado o score

O modelo de linguagem **não escolhe o número**. Para cada fonte, o modelo indica apenas a
posição (apoia, refuta ou neutro) e a relevância (0 a 1). O score é calculado em
`scoring.py`:

```
peso       = fiabilidade_do_domínio × relevância
A, R       = soma dos pesos que apoiam / refutam  (cada domínio conta uma vez por sentido)
score      = 50 + 50 × (A − R) / (A + R + 0,5)
confiança  = (A + R) / (A + R + 1)
A + R < 0,4  →  "Não verificável (evidência insuficiente)"
```

| Score   | Classificação               |
|---------|-----------------------------|
| ≥ 80    | Verdadeiro                  |
| 60–80   | Maioritariamente verdadeiro |
| 40–60   | Misto / inconclusivo        |
| 20–40   | Maioritariamente falso      |
| < 20    | Falso                       |

O score global é a média ponderada pela confiança. Passa a "Enganador" quando uma
afirmação é falsa com confiança alta, mesmo que as outras sejam verdadeiras.

**Esta fórmula é uma heurística transparente, não um método cientificamente validado.**
Os limiares e as listas de fiabilidade devem ser calibrados com casos reais, por exemplo
comparando os resultados com veredictos publicados pelo Polígrafo, Observador Fact Check,
AFP ou Reuters.

### Fiabilidade das fontes

`sources.py` contém uma lista inicial de domínios por nível: fact-checkers, fontes
oficiais ou científicas, agências e media de referência, enciclopédias e redes sociais.
Pode estendê-la com um ficheiro JSON indicado em `POLYGRAFO_SOURCES_FILE`:

```json
{ "media regional": { "reliability": 0.65, "domains": ["acorianooriental.pt"] } }
```

A lista é um ponto de partida. Não é uma classificação oficial. Confirme os signatários
atuais da IFCN em <https://ifcncodeofprinciples.poynter.org/signatories>.

## Limitações (importante)

- **Acesso às redes sociais.** A Meta (Facebook e Instagram) e o TikTok não disponibilizam
  uma API pública para ler publicações de terceiros. A
  [Meta Content Library](https://transparency.meta.com/researchtools/meta-content-library)
  e a [TikTok Research API](https://developers.tiktok.com/products/research-api/) estão
  reservadas a investigadores aprovados. Esta aplicação usa o `yt-dlp` e os metadados
  públicos, que funcionam em muitos casos mas não em todos: publicações privadas ou que
  exigem sessão iniciada não podem ser lidas, e as plataformas mudam frequentemente.
  Nesses casos, cole o texto ou envie uma captura de ecrã.
- **Termos de Serviço.** A extração automática pode violar os termos das plataformas.
  Use a aplicação para fins pessoais e com moderação.
- **Imagens e vídeos manipulados.** A aplicação verifica o que é *afirmado*. Não deteta
  deepfakes nem edições de imagem, e não faz pesquisa reversa de imagens. Para isso,
  use ferramentas dedicadas, como o InVID/WeVerify.
- **Erros do modelo.** O modelo pode classificar mal a posição de uma fonte. Por isso,
  cada prova é apresentada com ligação e excerto, e os URLs que não apareceram na
  pesquisa real são descartados. Leia as provas antes de tirar conclusões.
- **Atualidade.** Notícias de última hora podem ainda não ter fontes fiáveis. O resultado
  "Não verificável" é uma resposta legítima.
- **Custo.** Cada afirmação pode usar até 6 pesquisas web e várias chamadas ao modelo.
  Ajuste `POLYGRAFO_MAX_CLAIMS` e `POLYGRAFO_MAX_SEARCHES`.

## Testes

```bash
pip install pytest httpx
python -m pytest -q
```

Os testes cobrem o score, a classificação de fontes, a extração Open Graph, a
proteção por senha, as análises em segundo plano e a
orquestração. Esta última usa um cliente falso, sem chamadas reais à API.

## Próximos passos possíveis

- Pesquisa reversa de imagens e análise de metadados (EXIF) para detetar imagens fora de contexto.
- Histórico local (SQLite) de verificações e reutilização de resultados.
- Extensão de browser para verificar a publicação aberta com um clique.
- Calibração do score com um conjunto de casos já verificados por fact-checkers.
