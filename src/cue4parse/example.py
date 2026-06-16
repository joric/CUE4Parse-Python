import time
from cue4parse import *

GAME_DIR = r"E:\Games\Subnautica2\Subnautica2\Content\Paks"
MAPPINGS_FILE = r"E:\Games\Subnautica2\Subnautica2.usmap"

def main():
    start = time.perf_counter()

    Log.Logger = with_console(LoggerConfiguration().MinimumLevel.Verbose()).CreateLogger()

    version = VersionContainer(EGame.GAME_UE5_6, ETexturePlatform.DesktopMobile)
    provider = DefaultFileProvider(GAME_DIR, SearchOption.TopDirectoryOnly, version, StringComparer.OrdinalIgnoreCase)

    provider.MappingsContainer = FileUsmapTypeMappingsProvider(MAPPINGS_FILE)
    provider.Initialize()

    provider.SubmitKey(FGuid(0,0,0,0), FAesKey(bytearray(32)))
    provider.PostMount()

    package_path = 'Subnautica2/Content/Maps/Main/L_Main.umap'

    ok, package = provider.TryLoadPackage(package_path)

    exports = package.GetExports()

    filter = lambda name: 'Lifepod' in str(name)

    for export in exports:
        if not filter(export.ExportType):
            continue
        print(export.ExportType, export.Name)

    print(f'Finished in {time.perf_counter() - start:.4f}s')

if __name__ == '__main__':
    raise SystemExit(main())
