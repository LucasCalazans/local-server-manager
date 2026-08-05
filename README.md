# Server App Manager

Painel desktop (Windows) para iniciar/parar suas aplicacoes de desenvolvimento
que rodam no **WSL Ubuntu** — front (npm) e back (Python) — por botoes, sem
precisar abrir o terminal e digitar os comandos de cada projeto.

## O que faz

- **Abas de ambiente**: cada aba eh uma maquina. A padrao eh esta (WSL local);
  outras podem ser remotas via `ssh`, e ai os botoes controlam os servicos de
  la sem sair daqui.
- Lista suas aplicacoes em cards; cada aplicacao tem um ou mais **servicos**
  (ex.: Backend e Frontend).
- Botoes por servico: **Iniciar**, **Parar**, **Reiniciar** (para e sobe de
  novo) e **Abrir** (abre a URL no navegador do Windows).
- Botao **Logs** na barra superior: painel lateral unico com os logs de todos os
  servicos, identificados por aplicacao/servico.
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

## Ambientes remotos (ssh)

Em **Configuracoes → Ambientes**, um ambiente do tipo `ssh` executa tudo na
maquina remota. Os comandos saem pelo **WSL desta maquina** e entram por `ssh`
no host — nao pelo `ssh.exe` do Windows. Isso eh de proposito: eh o WSL que tem
o `~/.ssh/config` (com os aliases) e a rota da tailnet; o Windows nao alcanca a
faixa `100.x` quando ha VPN ocupando a mesma CGNAT.

Campos do ambiente:

| campo | para que serve |
|---|---|
| **Host ssh** | alias ou `user@host` — precisa autenticar sem senha (`BatchMode`) |
| **Distro WSL** | a distro **local** de onde o `ssh` sai |
| **Shell init** | roda na maquina remota, antes de cada comando |
| **Host das URLs** | substitui `localhost` ao abrir no navegador (ex.: `192.168.0.3`), ja que o localhost de la nao eh o daqui |

Status e logs continuam funcionando: o estado dos servicos, os probes de URL e
os `health_command` viajam todos numa **unica** ida de `ssh` por ciclo, e os
logs vem por um `tail -F` remoto, prefixados com o nome do ambiente.

Duas limitacoes conhecidas:

- Servicos com `runtime="windows"` aparecem com os botoes **desabilitados** num
  ambiente ssh: eles subiriam numa sessao Windows sem desktop (a do sshd), onde
  nenhuma janela apareceria. Sobem so na maquina de la.
- O **Host das URLs** so resolve dentro da LAN. Fora dela, use um tunel ssh
  (`ssh -N -L 5001:localhost:5001 <host>`) e deixe o campo vazio.

## Observacoes

- Os logs de cada servico ficam em `/tmp/appmgr-<id>.log` dentro do WSL.
- O botao **Logs** abre um painel lateral unico com a saida de **todos** os servicos ao
  vivo, cada linha prefixada pela origem (`Aplicacao · Servico`) numa cor
  propria. Do lado do WSL isso eh um `tail -F` unico sobre todos os arquivos.
- Fechar o painel **nao** para as aplicacoes; elas continuam rodando no WSL e o
  status eh re-detectado quando voce reabre.
