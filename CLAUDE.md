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

Sincronizar os arquivos alterados pro D e compilar la (build nativo, disco
Windows):

```bash
cp server_app_manager/mainwindow.py /mnt/d/build/local-server-manager/server_app_manager/
cd /mnt/d/build/local-server-manager && python.exe -m PyInstaller --noconfirm --windowed --collect-data qtawesome --hidden-import PySide6.QtNetwork --name "ServerAppManager" main.py
```

Esse eh exatamente o comando do `build.bat`, menos os `pip install` do inicio: o
Python do Windows (3.14) ja tem PySide6, QtAwesome e PyInstaller instalados.

`cmd.exe /c build.bat` a partir do repo do WSL **nao** funciona — o `cmd` recusa
caminho UNC (`\\wsl.localhost\...`) como diretorio de trabalho. Chamar o
`python.exe` direto, com o cwd do bash em `/mnt/d/...`, resolve.

Alteracao em `.py` so aparece no EXE depois de rebuildar. Pra testar rapido sem
compilar, `run.bat` roda direto do source (precisa de Python + PySide6 no
Windows).

## Armadilhas ja encontradas

1. **Janela do Explorer aberta em `dist\ServerAppManager` trava o build**
   (`WinError 32`). Pior: o PyInstaller apaga o `dist` antigo **antes** de
   falhar, entao o build que funcionava se perde. Fechar as janelas antes:

   ```bash
   powershell.exe -NoProfile -Command "(New-Object -ComObject Shell.Application).Windows() | Where-Object { \$_.LocationURL -like '*local-server-manager*' } | ForEach-Object { \$_.Quit() }"
   ```

2. **`mv`/`rm` de diretorio em `/mnt/d` dando "Permission denied" pelo WSL** quase
   nunca eh permissao — eh handle aberto do lado Windows. Checar quem segura
   antes de insistir.

3. **Quando nao da pra substituir a pasta**, escrever arquivos *dentro* dela
   costuma funcionar mesmo assim. Buildar em outro lugar e espelhar:

   ```bash
   powershell.exe -NoProfile -Command "robocopy '<origem>' 'D:\build\local-server-manager\dist\ServerAppManager' /E /NFL /NDL /NJH /NP"
   ```
