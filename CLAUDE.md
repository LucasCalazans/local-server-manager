# CLAUDE.md

## Onde mora o build

Duas copias do projeto, com papeis diferentes:

| Caminho | Papel |
| --- | --- |
| `/home/calazans/projects/local-server-manager` (WSL) | **Source de verdade.** Editar aqui. Tem o git com o historico completo. |
| `D:\build\local-server-manager` (`/mnt/d/...` pelo WSL) | **Build.** O EXE que o usuario roda de fato sai daqui. Tem uma copia do source (git proprio, historico defasado) usada so pra compilar. |

O executavel em uso:
`D:\build\local-server-manager\dist\ServerAppManager\ServerAppManager.exe`

**Nao gerar `dist/` nem `build/` dentro do repo do WSL.** Sao ~140 MB de lixo
num filesystem que o Windows so acessa por UNC (lento) e que nao eh de onde o
app roda. Se aparecerem la, foi engano — apagar.

## Como rebuildar

Sincronizar os arquivos alterados pro D, compilar num `--distpath` novo e
espelhar por cima do definitivo:

```bash
cp server_app_manager/process.py /mnt/d/build/local-server-manager/server_app_manager/
cd /mnt/d/build/local-server-manager && python.exe -m PyInstaller --noconfirm --windowed --collect-data qtawesome --hidden-import PySide6.QtNetwork --name "ServerAppManager" --distpath "D:\build\local-server-manager\dist-new" main.py
powershell.exe -NoProfile -Command "robocopy 'D:\build\local-server-manager\dist-new\ServerAppManager' 'D:\build\local-server-manager\dist\ServerAppManager' /MIR /NFL /NDL /NJH /NP; exit 0"
powershell.exe -NoProfile -Command "Remove-Item -LiteralPath 'D:\build\local-server-manager\dist-new' -Recurse -Force"
```

O `--distpath` nao eh capricho: ver armadilha 1. Fora isso o comando eh o do
`build.bat`, menos os `pip install` do inicio — o Python do Windows (3.14) ja
tem PySide6, QtAwesome e PyInstaller instalados.

`cmd.exe /c build.bat` a partir do repo do WSL **nao** funciona — o `cmd` recusa
caminho UNC (`\\wsl.localhost\...`) como diretorio de trabalho. Chamar o
`python.exe` direto, com o cwd do bash em `/mnt/d/...`, resolve.

Alteracao em `.py` so aparece no EXE depois de rebuildar. Pra testar rapido sem
compilar, `run.bat` roda direto do source (precisa de Python + PySide6 no
Windows).

## Armadilhas ja encontradas

1. **`D:\build\local-server-manager\dist\ServerAppManager` vive presa por
   algum processo** (`WinError 32` ao tentar apagar/renomear). Ja aconteceu
   duas vezes, a segunda **sem nenhuma janela do Explorer aberta** — fechar o
   Explorer nao basta (uma pasta irma, criada na hora, apaga numa boa).

   **Um dos donos do handle ja foi identificado: o proprio app rodando.**
   O `ServerAppManager.exe` aberto segura o EXE que se quer sobrescrever.
   O sintoma pelo robocopy nao eh erro, eh *travamento*: o default eh
   `/R:1000000 /W:30`, entao ele reenta pra sempre em silencio — 8 minutos
   com zero arquivos copiados e nenhuma mensagem. Fechar o app destrava e o
   robocopy conclui sozinho. **Cheque o processo antes de espelhar:**

   ```bash
   powershell.exe -NoProfile -Command "Get-Process ServerAppManager -ErrorAction SilentlyContinue"
   ```

   E use `/R:2 /W:2` no robocopy pra ele falhar rapido em vez de pendurar.

   O estrago: o PyInstaller apaga o `dist` **antes** de falhar, entao a
   tentativa destroi o build que funcionava e nao entrega o novo. Por isso o
   `--distpath` acima — buildar em pasta nova nunca esbarra no lock, e
   `robocopy /MIR` escreve *dentro* da pasta presa, o que funciona mesmo
   quando apagar a pasta nao funciona.

2. **`mv`/`rm` de diretorio em `/mnt/d` dando "Permission denied" pelo WSL** quase
   nunca eh permissao — eh o mesmo `WinError 32` visto de outro angulo.

3. **`checking PYZ` sem `Building PYZ` no log = cache reusado.** Nem sempre eh
   erro (se a analise anterior ja tinha o source novo, o cache esta correto),
   mas nao confie: confira se o fix entrou mesmo no EXE.

   ```bash
   python.exe -c "from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader; c=CArchiveReader(r'D:\build\local-server-manager\dist\ServerAppManager\ServerAppManager.exe'); n=[x for x in c.toc if x.endswith('.pyz')][0]; open(r'C:\Users\calaz\AppData\Local\Temp\pyz.tmp','wb').write(c.extract(n)); z=ZlibArchiveReader(r'C:\Users\calaz\AppData\Local\Temp\pyz.tmp'); print(z.extract('server_app_manager.process').co_consts[:3])"
   ```
