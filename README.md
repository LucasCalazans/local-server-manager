# Server App Manager

Painel desktop (Windows) para iniciar/parar suas aplicacoes de desenvolvimento
que rodam no **WSL Ubuntu** — front (npm) e back (Python) — por botoes, sem
precisar abrir o terminal e digitar os comandos de cada projeto.

## O que faz

- Lista suas aplicacoes em cards; cada aplicacao tem um ou mais **servicos**
  (ex.: Backend e Frontend).
- Botoes por servico: **Iniciar**, **Parar** e **Abrir** (abre a URL no
  navegador do Windows).
- Indicador de **status** (verde = rodando, cinza = parado), atualizado
  automaticamente — inclusive depois de reabrir o painel.
- Cadastro pela propria interface (botao **+ Aplicacao**) **ou** editando o
  arquivo de configuracao JSON.

Os comandos sao disparados no WSL via:

```
wsl.exe -d <distro> -- bash -lc "<comando>"
```

Cada servico roda no proprio *process group*, entao **Parar** derruba tambem os
processos filhos (ex.: o `vite`/`esbuild` que o `npm run dev` cria).

## Pre-requisitos

- Windows com **WSL2** e uma distro instalada (ex.: Ubuntu).
- **Python 3.10+** no Windows (para rodar/empacotar). Baixe em python.org.

## Como rodar (desenvolvimento)

```bat
pip install -r requirements.txt
run.bat
```

## Gerar o .exe (sem precisar de Python para usar)

```bat
build.bat
```

O executavel fica em `dist\ServerAppManager.exe`. Pode criar um atalho dele na
area de trabalho.

## Configuracao

Na primeira execucao eh criado o arquivo:

```
C:\Users\<voce>\.server-app-manager\config.json
```

Veja `config.example.json` para o formato. Campos principais:

- `distro`: nome da distro WSL (ex.: `Ubuntu`). Vazio usa a distro padrao.
- `shell_init`: trecho de shell prependido a **todo** comando. Use para
  carregar o `nvm` quando o `npm` vem dele (o `~/.bashrc` costuma sair cedo em
  shell nao-interativo). Exemplo ja incluido no `config.example.json`.
- `applications[].services[]`: `name`, `directory` (caminho **dentro do WSL**),
  `command` e `url` (opcional).

> Dica: os caminhos em `directory` sao caminhos do Linux/WSL
> (ex.: `/home/usuario/projeto`), nao caminhos do Windows.

## Observacoes

- Os logs de cada servico ficam em `/tmp/appmgr-<id>.log` dentro do WSL.
- Fechar o painel **nao** para as aplicacoes; elas continuam rodando no WSL e o
  status eh re-detectado quando voce reabre.
