from cue4parse import *

import tempfile
import fnmatch
import time
from importlib.metadata import version

export_directory = ""
overwrite_files = False

DEBUG = False

class ExportType(Flag):
    NONE = 0
    TEXTURE = auto()
    SOUND = auto()
    MESH = auto()
    ANIMATION = auto()
    OTHER = auto()

@dataclass
class CliOptions:
    sources: list[str]
    pak: str | None
    output: str | None
    package: list[str]
    config: list[str]
    game: str
    key: list[str]
    mappings: str | None
    format: str
    list_only: bool
    yes: bool
    verbose: bool
    mesh_format: str
    anim_format: str
    texture_format: str
    material_format: str
    lod_format: str
    socket_format: str
    nanite_format: str  # kept for parity (not assigned if enum unavailable)
    export_morph_targets: bool
    export_materials: bool
    export_hdr_as_hdr: bool
    compression: str

def norm_path(path: str) -> str:
    if not path:
        return "."
    return path.replace("/", os.sep).replace("\\\\", "\\")


def parse_enum(enum_type: Any, value: str, default_name: str | None = None) -> Any:
    # pythonnet enum access: getattr(EnumType, "ValueName")
    if hasattr(enum_type, value):
        return getattr(enum_type, value)
    for name in dir(enum_type):
        if name.lower() == value.lower():
            return getattr(enum_type, name)
    if default_name and hasattr(enum_type, default_name):
        print(f"Warning: Unknown value '{value}' for {enum_type.__name__}, using default '{default_name}'", file=sys.stderr)
        return getattr(enum_type, default_name)
    print(f"Warning: Unknown value '{value}' for {enum_type.__name__}, using default", file=sys.stderr)
    # best-effort default
    names = [n for n in dir(enum_type) if not n.startswith("_")]
    return getattr(enum_type, names[0]) if names else None


def check_file(out_path: Path, silent: bool = False) -> bool:
    skip = (not overwrite_files) and out_path.exists()
    if not silent:
        if skip:
            Log.Warning("Already exists, skipping {Path}", norm_path(str(out_path)))
        else:
            Log.Information("Writing {Path}", norm_path(str(out_path)))
    return not skip


def write_to_log(_folder: str, _log_message: str, counter: list[int]) -> None:
    counter[0] += 1


def write_to_file(folder: str, file_name: str, data: bytes, log_message: str, counter: list[int]) -> None:
    out_path = Path(export_directory) / folder / file_name
    if not check_file(out_path):
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
    write_to_log(folder, log_message, counter)

def save_json(folder: str, name: str, exports: Any, counter: list[int]) -> None:
    #text = JsonConvert.SerializeObject(exports, Formatting.Indented) # alternative way

    serializer = JsonSerializer();
    serializer.Formatting = Formatting.Indented;

    output_to_stdout = export_directory==""
    if output_to_stdout:
        writer = JsonTextWriter(Console.Out)
        serializer.Serialize(writer, exports)
        writer.Flush()
        return

    file_name = f"{Path(name).stem}.json"
    out_path = Path(export_directory) / folder / file_name

    if not check_file(out_path):
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)

    stream = StreamWriter(str(out_path), False, Encoding.UTF8);
    try:
        writer = JsonTextWriter(stream);
        try:
            serializer.Serialize(writer, exports);
            writer.Flush()
        finally:
            writer.Close()
    finally:
        stream.Close()

    write_to_log(folder, name, counter)


def save_raw(folder: str, package, provider, counter: list[int]) -> None:
    name = str(package.Name)
    out_path = Path(export_directory) / folder / name
    if not check_file(out_path):
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = bytes(provider.Files[package.Path].Read())
    write_to_file(folder, name, data, name, counter)


def try_load_locmeta(package) -> tuple[bool, Any]:
    ok, reader = package.TryCreateReader()
    if not ok or reader is None:
        return False, None
    try:
        return True, FTextLocalizationMetaDataResource(reader)
    except Exception:
        return False, None


def try_load_locres(package) -> tuple[bool, Any]:
    ok, reader = package.TryCreateReader()
    if not ok or reader is None:
        return False, None
    try:
        return True, FTextLocalizationResource(reader)
    except Exception:
        return False, None


def save_texture(folder: str, texture: UTexture, platform: ETexturePlatform, options: ExporterOptions, counter: list[int], name_prefix='') -> None:
    out_base = Path(export_directory) / folder / str(texture.Name)
    for ext in (".png", ".hdr"):
        p = out_base.with_suffix(ext)
        if not check_file(p, silent=True):
            check_file(p, silent=False)
            return

    if isinstance(texture, UTexture2DArray):
        bitmaps = list(TextureDecoder.DecodeTextureArray(texture, platform))
    else:
        bitmap = TextureDecoder.Decode(texture, platform)
        if isinstance(texture, UTextureCube):
            bitmap = CubemapConverter.ToPanorama(bitmap) if bitmap is not None else None
        bitmaps = [bitmap]

    for bitmap in bitmaps or []:
        if bitmap is None:
            continue
        result = TextureEncoder.Encode(bitmap, options.TextureFormat, options.ExportHdrTexturesAsHdr)
        if isinstance(result, tuple):
            encoded, extension = result
        else:
            encoded, extension = result, "png"
        file_name = f"{name_prefix}{texture.Name}.{extension}"
        write_to_file(folder, file_name, bytes(encoded), f"{file_name} ({bitmap.Width}x{bitmap.Height})", counter)


def filter_paths(paths: Iterable[str], pattern: str) -> list[str]:
    return [p for p in paths if fnmatch.fnmatch(p, pattern)]


def execute(options: CliOptions) -> int:
    global export_directory, overwrite_files

    overwrite_files = options.yes

    if options.verbose:
        Log.Logger = LoggerConfiguration().MinimumLevel.Verbose().WriteTo.Console().CreateLogger()
    else:
        Log.Logger = LoggerConfiguration().MinimumLevel.Fatal().WriteTo.Console().CreateLogger()

    try:
        game_version = parse_enum(EGame, options.game, "GAME_UE5_LATEST")
    except Exception:
        raise ValueError(f"Invalid game version: {options.game}")

    if options.mappings and (not Path(options.mappings).exists()):
        print(f"Mappings not found: {options.mappings}", file=sys.stderr)
        return 1

    version = VersionContainer(game_version, ETexturePlatform.DesktopMobile)

    single_pak_mode = bool(options.pak)
    if single_pak_mode:
        if not Path(options.pak).exists():
            print(f"Pak file not found: {options.pak}", file=sys.stderr)
            return 1
        print(f"Loading single pak: {norm_path(options.pak)}...", file=sys.stderr)
        pak_dir = str(Path(options.pak).resolve().parent)
        provider = DefaultFileProvider(pak_dir, SearchOption.TopDirectoryOnly, VersionContainer(game_version))
    else:
        directory = options.sources[0] if options.sources else None
        if not directory:
            return 0
        print(f"Loading {norm_path(directory)}...", file=sys.stderr)
        if directory.endswith(".apk"):
            provider = ApkFileProvider(directory, VersionContainer(game_version))
        else:
            provider = DefaultFileProvider(directory, SearchOption.AllDirectories, VersionContainer(game_version), StringComparer.OrdinalIgnoreCase)

    if options.mappings and Path(options.mappings).exists():
        provider.MappingsContainer = FileUsmapTypeMappingsProvider(options.mappings)

    oodle_path = os.path.join(tempfile.gettempdir(), str(OodleHelper.OodleFileName))
    OodleHelper.DownloadOodleDll(oodle_path)
    OodleHelper.Initialize(oodle_path)

    zlib_path = os.path.join(tempfile.gettempdir(), str(ZlibHelper.DLL_NAME))
    ZlibHelper.DownloadDll(zlib_path)
    ZlibHelper.Initialize(zlib_path)

    if single_pak_mode:
        provider.RegisterVfs(options.pak)
    else:
        provider.Initialize()

    for key_entry in options.key:
        provider.SubmitKey(FGuid(), FAesKey(key_entry))

    provider.SubmitKey(FGuid(0,0,0,0), FAesKey(bytearray(32)))
    provider.PostMount()

    try:
        provider.ChangeCulture(provider.GetLanguageCode(ELanguage.English))
    except Exception as exc:
        msg = "expected for single-pak mode" if single_pak_mode else "culture loading failed"
        Log.Warning(f"Warning: Culture loading failed ({msg}): {exc}")

    print(f"Total assets: {provider.Files.Count}", file=sys.stderr)
    print(f"Output format: {options.format}", file=sys.stderr)

    detex_path = os.path.join(tempfile.gettempdir(), str(DetexHelper.DLL_NAME))
    if not Path(detex_path).exists():
        DetexHelper.LoadDllAsync(detex_path).GetAwaiter().GetResult()
    DetexHelper.Initialize(detex_path)

    package_paths: list[str] = []
    for list_file in options.config:
        if list_file and Path(list_file).exists():
            print(f"Loading file list: {norm_path(list_file)}", file=sys.stderr)
            for line in Path(list_file).read_text(encoding="utf-8", errors="ignore").splitlines():
                t = line.strip()
                if not t or t.startswith("#") or t.startswith("["):
                    continue
                package_paths.append(t)

    for item in options.package:
        if item:
            package_paths.append(item)

    if not package_paths:
        package_paths = ["*"]

    packages = []
    keys = list(provider.Files.Keys)
    for path in package_paths:
        if any(ch in path for ch in ("*", "?")):
            matched_keys = filter_paths(keys, path)
            matched = [provider.Files[k] for k in matched_keys]
            print(f"Added wildcard: {path} ({len(matched)} matches)", file=sys.stderr)
        else:
            ok, obj = provider.Files.TryGetValue(path)
            matched = [obj] if ok else []
        packages.extend(matched)

    if not packages:
        print("No matches, exiting.", file=sys.stderr)
        return 0

    export_type = ExportType.TEXTURE | ExportType.SOUND | ExportType.MESH | ExportType.ANIMATION | ExportType.OTHER

    exp_options = ExporterOptions()
    exp_options.LodFormat = parse_enum(ELodFormat, options.lod_format, "AllLods")
    exp_options.MeshFormat = parse_enum(EMeshFormat, options.mesh_format, "ActorX")
    exp_options.AnimFormat = parse_enum(EAnimFormat, options.anim_format, "ActorX")
    exp_options.MaterialFormat = parse_enum(EMaterialFormat, options.material_format, "AllLayersNoRef")
    exp_options.TextureFormat = parse_enum(ETextureFormat, options.texture_format, "Png")
    exp_options.CompressionFormat = parse_enum(EFileCompressionFormat, options.compression, "None")
    exp_options.Platform = version.Platform
    exp_options.SocketFormat = parse_enum(ESocketFormat, options.socket_format, "Bone")
    exp_options.ExportMorphTargets = options.export_morph_targets
    exp_options.ExportMaterials = options.export_materials
    exp_options.ExportHdrTexturesAsHdr = options.export_hdr_as_hdr

    needs_output_dir = (not options.list_only) and options.format not in ("csv", "json")
    if not options.output:
        if needs_output_dir:
            print("Output directory is not specified. Use -o <dir> or use -f json/csv/-l for stdout output.", file=sys.stderr)
            return 1
        export_directory = ""
    else:
        export_directory = norm_path(options.output)

    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    counter_lock = threading.Lock()
    export_count = [0]
    counter = 0
    start = time.monotonic()

    def process_package(package):
        folder = str(package.Path).rsplit("/", 1)[0] if "/" in str(package.Path) else ""
        ext = Path(str(package.Name)).suffix.lower()
        target_format = options.format

        if target_format != "raw":
            if ext == ".umap" and target_format != "png":
                target_format = "json"
            elif ext == ".locmeta":
                ok, locmeta = try_load_locmeta(package)
                if ok:
                    save_json(folder, str(package.Name), locmeta, export_count)
                    return True
            elif ext == ".locres":
                ok, locres = try_load_locres(package)
                if ok:
                    save_json(folder, str(package.Name), locres, export_count)
                    return True

        ok, pkg = provider.TryLoadPackage(package)
        if not ok or pkg is None:
            if ext in (".uasset", ".umap"):
                raise RuntimeError("Could not load standard asset, check game version, mappings or keys.")
            if target_format in ("auto", "raw"):
                target_format = "raw"
            else:
                return True

        if target_format == "raw":
            save_raw(folder, package, provider, export_count)
            return True

        if target_format == "json":
            save_json(folder, str(package.Name), pkg.GetExports(), export_count)
            return True

        if target_format not in ("auto", "png"):
            return True

        if target_format == "png":
            local_export_type = ExportType.TEXTURE
        else:
            local_export_type = ExportType.TEXTURE | ExportType.SOUND | ExportType.MESH | ExportType.ANIMATION | ExportType.OTHER

        parsed = False

        for i in range(pkg.ExportMapLength):
            pointer = FPackageIndex(pkg, i + 1).ResolvedObject
            if pointer is None or pointer.Object is None:
                continue
            dummy = AbstractUePackage.ConstructObject(pkg, pointer.Class, pkg)
            if dummy is None:
                continue

            value = pointer.Object.Value
            if isinstance(dummy, UTexture) and (ExportType.TEXTURE in local_export_type) and isinstance(value, UTexture):

                name_prefix = folder if ext != ".umap" else str(package.Path).rsplit(".", 1)[0]+'.'+str(i)+'.'
                try:
                    save_texture(folder, value, exp_options.Platform, exp_options, export_count, name_prefix)
                except Exception as exc:
                    Log.Warning("failed to decode {ValueName}: {Error}", value.Name, exc)
                parsed = True

            elif isinstance(dummy, (USoundWave, UAkMediaAssetData)) and (ExportType.SOUND in local_export_type):
                fmt_ref = clr.Reference[str]("")
                data_ref = clr.Reference[object](None)
                value.Decode(True, fmt_ref, data_ref)
                if data_ref.Value is not None:
                    file_name = f"{value.Name}.{str(fmt_ref.Value).lower()}"
                    write_to_file(folder, file_name, bytes(data_ref.Value), file_name, export_count)
                parsed = True

            elif isinstance(dummy, (UAnimSequenceBase, USkeletalMesh, UStaticMesh, USkeleton)) and (
                ExportType.ANIMATION in local_export_type or ExportType.MESH in local_export_type
            ):
                exporter = CUE4Exporter(value, exp_options)
                ok_write, _, file_path = exporter.TryWriteToDir(DirectoryInfo(export_directory), None, None)
                if ok_write:
                    write_to_log(folder, os.path.basename(str(file_path)), export_count)
                parsed = True

        if not parsed and (target_format == 'json' or target_format == 'auto'):
            save_json(folder, str(package.Name), pkg.GetExports(), export_count)

        return True

    if options.list_only:
        for package in packages:
            if options.format == "csv":
                print(f"{package.Path},{provider.Files[package.Path].Size}")
            else:
                print(package.Path)
    else:

        max_workers = os.cpu_count() or 4 if not DEBUG else 1
        fatal_error = [None]  # shared error slot

        print(f"Using parallel processing, {max_workers} threads", file=sys.stderr)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_package, pkg): pkg for pkg in packages}
            for future in as_completed(futures):
                if fatal_error[0]:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                with counter_lock:
                    counter += 1
                    if not options.verbose:
                        print(f"Exporting package {counter} of {len(packages)}...      \r", end="", file=sys.stderr)
                try:
                    future.result()
                except RuntimeError as e:
                    fatal_error[0] = e
                    print(str(e), file=sys.stderr)

        if fatal_error[0]:
            return 1

    elapsed = time.monotonic() - start

    if not options.verbose:
        print(f"Processed {len(packages)} packages in {elapsed:.2f}s", file=sys.stderr)

    Log.Information(f"Processed {len(packages)} packages in {elapsed:.2f}s")
    return 0

import argparse

class CustomHelpFormatter(argparse.RawTextHelpFormatter):
    def __init__(self, prog):
        super().__init__(prog, max_help_position=60, width=120)
        self.show_extended = False
    def _get_help_string(self, action):
        help_string = action.help or ''
        if action.default is not None and action.default != argparse.SUPPRESS:
            if action.default == [] or action.default is False:
                return help_string
            if '%(default)' not in help_string:
                help_string += ' (default: %(default)s)'
        return help_string

examples = [
    ["Export all package names to a text file:", "cue4parse -i MyGame -l > packages.txt"],
    ["Export a single package to stdout in json format:", "cue4parse -i MyGame -p Assets/MyAsset.uasset -f json"],
    ["Export multiple packages matching wildcard patterns to a directory:", "cue4parse -i MyGame -p */Textures* -p */Icons* -o Exports"],
    ["Export packages from list, overwrite existing files:", "cue4parse -i MyGame -c packages.txt -o Exports -y"],
    ["Export with PSK meshes and PSA animations:", "cue4parse -i MyGame -p */SkeletalMeshes/* -o Exports --mesh-format ActorX --anim-format ActorX"],
    ["Process a single .pak file:", "cue4parse --pak MyMod.pak -o Exports -m Mappings.usmap -g GAME_UE5_1"],
]

parser = argparse.ArgumentParser(
    prog="cue4parse",
    description=f"CUE4Parse-Python {version('cue4parse')}: a command line tool to extract resources from Unreal Engine games",
    epilog='\n\n'.join(f'{a}\n    {b}'for a,b in examples),
    formatter_class=CustomHelpFormatter,
    add_help = True,
)

parser.add_argument("-i", "--input", metavar="INPUT", action="append", default=[], dest="sources", help="Input game directory or pak/asset file (repeatable)")
parser.add_argument("-o", "--output", help="Output directory (optional for list/json/csv modes)")
parser.add_argument("-p", "--package", action="append", default=[], help="Package path or wildcard pattern (repeatable)")
parser.add_argument("-c", "--config", action="append", default=[], help="Package list file (repeatable)")
parser.add_argument("-g", "--game", default="GAME_UE5_LATEST", help="Game version")
parser.add_argument("-k", "--key", action="append", default=[], help="AES key in hex format (repeatable)")
parser.add_argument("-m", "--mappings", help="Mappings file")
parser.add_argument("-f", "--format", default="auto", help="Output format: auto, raw, json, csv, png")
parser.add_argument("-l", "--list", action="store_true", dest="list_only", help="List matching packages (supports auto and csv)")
parser.add_argument("-y", "--yes", action="store_true", help="Overwrite existing files")
parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")

# more options
parser.add_argument("--pak", help="Single .pak file to process (no directory scanning)")
parser.add_argument("--mesh-format", default="ActorX", help="Mesh format: ActorX (psk), Gltf2 (glb), UEFormat (uemodel), OBJ")
parser.add_argument("--anim-format", default="ActorX", help="Animation format: ActorX (psa), UEFormat (ueanim)")
parser.add_argument("--texture-format", default="Png", help="Texture format: Png, Jpeg, Tga, Dds")
parser.add_argument("--material-format", default="AllLayersNoRef", help="Material format: FirstLayer, AllLayersNoRef, AllLayers")
parser.add_argument("--lod-format", default="AllLods", help="LOD format: FirstLod, AllLods")
parser.add_argument("--socket-format", default="Bone", help="Socket format: Bone, Socket, None")
parser.add_argument("--nanite-format", default="AllLayersNaniteFirst", help="Nanite format: OnlyNaniteLOD, OnlyNormalLODs, AllLayersNaniteFirst, AllLayersNaniteLast")
parser.add_argument("--export-morph-targets", action=argparse.BooleanOptionalAction, default=True, help="Export morph targets")
parser.add_argument("--export-materials", action=argparse.BooleanOptionalAction, default=True, help="Export materials with meshes")
parser.add_argument("--export-hdr-as-hdr", action=argparse.BooleanOptionalAction, default=True, help="Export HDR textures as .hdr")
parser.add_argument("--compression", default="None", help="Compression: None, GZIP, ZSTD")

def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        parser.print_help()
        return 0
    return execute(parser.parse_args(argv))

if __name__ == "__main__":
    raise SystemExit(main())
