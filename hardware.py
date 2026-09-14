"""Hardware desta maquina e os pacotes que ele pede.

Tudo sai de /sys e /proc: nao precisa de root nem de programa extra, e roda
num Debian recem-instalado. A tela de Programas usa isto para mostrar so os
itens do catalogo que servem para o hardware encontrado.

Firmware nao e conferido arquivo por arquivo. Um modulo declara o firmware de
todos os chips que suporta (o btusb lista Realtek, MediaTek e Intel juntos), e
isso apontaria falta onde nao ha. Em vez disso, cada driver em uso indica o
pacote de firmware da sua familia.
"""

from __future__ import annotations

from pathlib import Path

SYS = Path("/sys")

# Driver em uso -> pacote de firmware. Padrao com * no fim e prefixo; sem ele,
# o nome tem de ser igual ("xe" como prefixo pegaria outros drivers)
FIRMWARE_POR_DRIVER = {
    "firmware-realtek": ("rtw_*", "rtw88*", "rtw89*", "rtl8*", "r8169", "r8152"),
    "firmware-iwlwifi": ("iwlwifi",),
    "firmware-atheros": ("ath9k_htc", "ath10k*", "ath11k*", "ath12k*", "ath6kl*"),
    "firmware-brcm80211": ("brcmfmac*", "brcmsmac"),
    "firmware-mediatek": ("mt7*",),
    "firmware-amd-graphics": ("amdgpu", "radeon"),
    "firmware-intel-graphics": ("i915", "xe"),
    "firmware-nvidia-graphics": ("nouveau",),
    "firmware-sof-signed": ("sof-audio*", "snd_sof*"),
    "firmware-libertas": ("libertas*", "mwifiex*"),
}

# o btusb serve a todos os fabricantes; quem diz o firmware e o id USB
BLUETOOTH_USB = {
    "0bda": ("Realtek", "firmware-realtek"),
    "8087": ("Intel", "firmware-iwlwifi"),
    "0e8d": ("MediaTek", "firmware-mediatek"),
    "0cf3": ("Qualcomm Atheros", "firmware-atheros"),
    "0a5c": ("Broadcom", ""),
}

VIDEO = {"0x8086": ("Intel", "video-intel"), "0x1002": ("AMD", "video-amd"),
         "0x10de": ("NVIDIA", "video-nvidia")}

# (fabricante USB, inicio do produto, nome); produto vazio vale para todos
LEITOR_DIGITAL = (
    ("27c6", "", "Goodix"), ("138a", "", "Validity"), ("147e", "", "Upek"),
    ("1c7a", "", "EgisTec"), ("10a5", "", "FPC"), ("2808", "", "Focal"),
    ("06cb", "00", "Synaptics"), ("04f3", "0c", "Elan"),
)

# tipos de gabinete da DMI que sao notebook, tablet ou conversivel
PORTATEIS = {"8", "9", "10", "11", "14", "30", "31", "32"}


def _ler(caminho: Path) -> str:
    try:
        return caminho.read_text(errors="replace").strip()
    except OSError:
        return ""


def _driver(dispositivo: Path) -> str:
    ligacao = dispositivo / "driver"
    try:
        return ligacao.resolve().name if ligacao.exists() else ""
    except OSError:
        return ""


def _bate(driver: str, padrao: str) -> bool:
    return driver.startswith(padrao[:-1]) if padrao.endswith("*") else driver == padrao


def _itens(pasta: Path, filtro: str = "*") -> list[Path]:
    try:
        return sorted(pasta.glob(filtro))
    except OSError:
        return []


def _fabricante_usb(dispositivo: Path) -> str:
    """idVendor do dispositivo, ou do de cima quando e uma interface (1-7:1.0)."""
    real = dispositivo.resolve()
    return (_ler(real / "idVendor") or _ler(real.parent / "idVendor")).lower()


def _processos() -> set[str]:
    nomes = set()
    for comm in _itens(Path("/proc"), "[0-9]*/comm"):
        nomes.add(_ler(comm))
    return nomes


def _non_free_firmware() -> bool:
    """As fontes do apt tem o componente onde o Debian poe firmware."""
    pasta = Path("/etc/apt/sources.list.d")
    arquivos = [Path("/etc/apt/sources.list"), *_itens(pasta, "*.list"),
                *_itens(pasta, "*.sources")]
    for arquivo in arquivos:
        for linha in _ler(arquivo).splitlines():
            if "non-free-firmware" in linha.split("#", 1)[0]:
                return True
    return False


def detectar() -> dict:
    """O que a maquina tem, as marcas que as regras do catalogo usam e o firmware pedido."""
    tags: set[str] = set()
    dispositivos: list[dict] = []
    firmware: dict[str, list[str]] = {}

    def achou(tag: str, nome: str, detalhe: str = "") -> None:
        tags.add(tag)
        dispositivos.append({"tipo": tag, "nome": nome, "detalhe": detalhe})

    def pede(pacote: str, driver: str) -> None:
        usos = firmware.setdefault(pacote, [])
        if driver not in usos:
            usos.append(driver)

    # processador; em VM o microcode nao se aplica, entao nem aparece
    cpu: dict[str, str] = {}
    for linha in _ler(Path("/proc/cpuinfo")).splitlines():
        chave, _, valor = linha.partition(":")
        cpu.setdefault(chave.strip(), valor.strip())
    virtual = "hypervisor" in cpu.get("flags", "").split()
    modelo = " ".join(cpu.get("model name", "").split())
    if not virtual:
        if cpu.get("vendor_id") == "GenuineIntel":
            achou("cpu-intel", "Processador", modelo)
        elif cpu.get("vendor_id") == "AuthenticAMD":
            achou("cpu-amd", "Processador", modelo)
    if "cpu-intel" in tags and _ler(SYS / "class/dmi/id/chassis_type") in PORTATEIS:
        tags.add("termico-intel")

    # video: qualquer placa da classe 0x03, com ou sem driver carregado
    for placa in _itens(SYS / "bus/pci/devices"):
        if not _ler(placa / "class").startswith("0x03"):
            continue
        marca, tag = VIDEO.get(_ler(placa / "vendor").lower(), ("", ""))
        if tag:
            achou(tag, f"Vídeo {marca}", _driver(placa) or "sem driver carregado")

    for rede in _itens(SYS / "class/net"):
        if (rede / "wireless").is_dir() or (rede / "phy80211").exists():
            achou("wifi", "Wi-Fi", f"{rede.name}, {_driver(rede / 'device') or 'sem driver'}")

    for hci in _itens(SYS / "class/bluetooth"):
        if ":" in hci.name:
            continue
        marca = BLUETOOTH_USB.get(_fabricante_usb(hci / "device"), ("", ""))[0]
        achou("bluetooth", "Bluetooth", ", ".join(filter(None, [hci.name, marca])))

    vistas: set[Path] = set()
    for video in _itens(SYS / "class/video4linux", "video*"):
        aparelho = (video / "device").resolve()
        if _driver(video / "device") != "uvcvideo" or aparelho in vistas:
            continue
        vistas.add(aparelho)
        achou("webcam", "Câmera", _ler(video / "name").split(":")[0])

    for fonte in _itens(SYS / "class/power_supply"):
        # scope=Device e bateria de mouse ou fone, nao da maquina
        if _ler(fonte / "type") == "Battery" and _ler(fonte / "scope") != "Device":
            nome = " ".join(filter(None, [_ler(fonte / "manufacturer"), _ler(fonte / "model_name")]))
            achou("bateria", "Bateria", nome or fonte.name)

    for usb in _itens(SYS / "bus/usb/devices"):
        fab, prod = _ler(usb / "idVendor").lower(), _ler(usb / "idProduct").lower()
        for vendor, inicio, nome in LEITOR_DIGITAL:
            if fab == vendor and prod.startswith(inicio):
                achou("leitor-digital", "Leitor de digital", nome)
                break

    # firmware: pelo driver de cada dispositivo real
    for barramento in ("pci", "usb", "sdio"):
        for aparelho in _itens(SYS / "bus" / barramento / "devices"):
            driver = _driver(aparelho)
            if not driver:
                continue
            if driver == "btusb":
                pacote = BLUETOOTH_USB.get(_fabricante_usb(aparelho), ("", ""))[1]
                if pacote:
                    pede(pacote, driver)
                continue
            for pacote, padroes in FIRMWARE_POR_DRIVER.items():
                if any(_bate(driver, p) for p in padroes):
                    pede(pacote, driver)

    # o servidor de som decide qual pacote de audio Bluetooth serve
    rodando = _processos()
    if "pipewire-pulse" in rodando:
        tags.add("som-pipewire")
    elif "pulseaudio" in rodando or Path("/usr/bin/pulseaudio").exists():
        tags.add("som-pulseaudio")
    elif Path("/usr/bin/pipewire-pulse").exists():
        tags.add("som-pipewire")

    # o tlp conflita com o power-profiles-daemon; o apt removeria um pelo outro
    if not Path("/usr/libexec/power-profiles-daemon").exists():
        tags.add("sem-power-profiles")
    if (SYS / "firmware/efi").is_dir():
        tags.add("uefi")

    return {"dispositivos": dispositivos, "tags": sorted(tags), "firmware": firmware,
            "virtual": virtual, "non_free_firmware": _non_free_firmware()}


def atende(item: dict, maquina: dict) -> bool:
    """O item do catalogo serve para esta maquina? Com lista, todas as marcas valem."""
    regra = item.get("hardware")
    if not regra:
        return False
    exigidas = [regra] if isinstance(regra, str) else list(regra)
    tags = set(maquina.get("tags", []))
    for marca in exigidas:
        if marca == "firmware":
            if item.get("pkg") not in maquina.get("firmware", {}):
                return False
        elif marca not in tags:
            return False
    return True
