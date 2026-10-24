"""Tables describing what the player can report and control.

Codes are written without the ``@0`` start characters; the client adds them.
Settings marked here are only turned into entities when the player answered
the matching status request during the (cached) capability probe.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- transport / power (media player) ---------------------------------------
CMD_POWER_ON = "PW00"
CMD_POWER_OFF = "PW01"
CMD_PLAY = "2353"
CMD_PAUSE = "2348"
CMD_STOP = "2354"
CMD_NEXT = "2332"
CMD_PREVIOUS = "2333"
CMD_MUTE_ON = "mt00"
CMD_MUTE_OFF = "mt01"

CAP_MUTE = "mt"

# --- status values ----------------------------------------------------------
DISC_STATUS: dict[str, str] = {
    "NC": "no_disc",
    "CI": "disc_in",
    "UF": "unformatted",
    "TO": "tray_open",
    "TC": "tray_closed",
    "TE": "tray_error",
    "LD": "loading",
}

PLAYBACK_STATUS: dict[str, str] = {
    "": "idle",
    "PL": "playing",
    "PP": "paused",
    "DVSF": "slow_forward",
    "DVSR": "slow_reverse",
    "DVFF": "fast_forward",
    "DVFR": "fast_reverse",
    "DVSP": "step",
    "ED": "menu",
    "DVSU": "setup",
    "DVTR": "track_menu",
    "DVHM": "home",
}

PLAYING_STATES = {"playing", "slow_forward", "slow_reverse", "fast_forward", "fast_reverse"}
PAUSED_STATES = {"paused", "step"}

MEDIA_TYPE: dict[str, str] = {
    "DVV": "dvd_video",
    "DVA": "dvd_audio",
    "CDA": "cd_audio",
    "CDR": "cd_rom",
    "SAC": "sacd",
    "DVR": "dvd_vr",
    "BDM": "bd_video",
    "BDA": "bdav",
    "AVH": "avchd",
    "DLN": "dlna",
    "EXT": "external_memory",
}

MUSIC_MEDIA = {"dvd_audio", "cd_audio", "sacd"}

AUDIO_FORMAT: dict[str, str] = {
    "DBD": "Dolby Digital",
    "DTS": "DTS",
    "MPG": "MPEG",
    "LPC": "LPCM",
    "PPC": "PPCM",
    "DSD": "DSD",
    "DD+": "Dolby Digital Plus",
    "DTH": "DTS-HD",
    "DHM": "DTS-HD Master Audio",
    "DLH": "Dolby TrueHD",
    "MP3": "MP3",
    "AAC": "AAC",
    "WMA": "WMA",
}

AUDIO_CHANNELS: dict[str, str] = {
    "1CH": "1.0",
    "2CH": "2.0",
    "21C": "2.1",
    "3CH": "3.0",
    "31C": "3.1",
    "4CH": "4.0",
    "41C": "4.1",
    "5CH": "5.0",
    "51C": "5.1",
    "6CH": "6.0",
    "61C": "6.1",
    "7CH": "7.0",
    "71C": "7.1",
    "8CH": "8.0",
    "L/R": "L/R",
    "RCH": "R",
    "LCH": "L",
}

# Status requests per poll stage.
POLL_STATUS = ("?PW", "?CD", "?ST")
POLL_MEDIA = ("?Tr", "?Tt", "?ti", "?at", "?al", "?ET", "?RM")
POLL_DETAILS = (
    "?PCTYP",
    "?PCAFMT",
    "?PCACH",
    "?PCDG+",
    "?PCDG-",
    "?DVSTC",
    "?fs",
    "?PCGp",
    "?PCTG",
)
# Values that belong to the loaded media; cleared when there is none.
MEDIA_KEYS = (
    "Tr",
    "Tt",
    "ti",
    "at",
    "al",
    "tl",
    "ET",
    "RM",
    "PCTYP",
    "PCAFMT",
    "BDACH",
    "PCDG+",
    "PCDG-",
    "DVSTC",
    "Fs",
    "PCGp",
    "PCTG",
)
# Bare answers (no "@0" code in the reply) are stored under these keys.
BARE_KEYS = {
    "?ET": "ET",
    "?RM": "RM",
    "?Tr": "Tr",
    "?Tt": "Tt",
    "?PCGp": "PCGp",
    "?PCTG": "PCTG",
    "?ST": "ST",
}


# --- settings -----------------------------------------------------------------
@dataclass(frozen=True)
class NumberSetting:
    """A level the player can report and set."""

    code: str
    key: str
    minimum: int
    maximum: int
    width: int
    unit: str | None = None
    enabled_default: bool = True
    icon: str | None = None


@dataclass(frozen=True)
class SelectSetting:
    """A choice the player can report and set (option -> code suffix).

    ``readback`` maps reported values to options when the player reports
    other codes than the ones it is set with (see the video resolution).
    """

    code: str
    key: str
    options: dict[str, str] = field(default_factory=dict)
    enabled_default: bool = True
    icon: str | None = None
    readback: dict[str, str] | None = None


@dataclass(frozen=True)
class SwitchSetting:
    """An on/off setting (suffix sent for on and for off)."""

    code: str
    key: str
    on: str
    off: str
    enabled_default: bool = True
    icon: str | None = None


@dataclass(frozen=True)
class ButtonCommand:
    """A remote-control style command without feedback."""

    key: str
    command: str
    enabled_default: bool = True
    icon: str | None = None


NUMBERS: tuple[NumberSetting, ...] = (
    NumberSetting("DVOV", "audio_output_level", -90, 10, 3, "dB", icon="mdi:volume-high"),
    NumberSetting("DVMV", "audio_maximum_volume", -10, 10, 3, "dB", False, "mdi:volume-plus"),
    NumberSetting("DVPABN", "video_brightness", -16, 16, 3, None, False, "mdi:brightness-6"),
    NumberSetting("DVPACT", "video_contrast", -16, 16, 3, None, False, "mdi:contrast-box"),
    NumberSetting("DVPAHU", "video_hue", -9, 9, 2, None, False, "mdi:palette"),
    NumberSetting("DVPASR", "video_saturation", -9, 9, 2, None, False, "mdi:invert-colors"),
)

SELECTS: tuple[SelectSetting, ...] = (
    SelectSetting(
        "DVVR",
        "video_resolution",
        {
            "auto": "1",
            "480i_576i": "2",
            "480p_576p": "3",
            "720p": "4",
            "1080i": "5",
            "1080p": "6",
        },
        icon="mdi:monitor-screenshot",
        # Measured: the player reports 7 while set to 1080p, so the reported
        # values run one higher than the documented set codes 1-6. Whether the
        # set codes are shifted too is checked on the first change (select.py).
        readback={
            "2": "auto",
            "3": "480i_576i",
            "4": "480p_576p",
            "5": "720p",
            "6": "1080i",
            "7": "1080p",
        },
    ),
    SelectSetting(
        "DVAr",
        "video_aspect_ratio",
        {
            "wide_16_9": "9W",
            "wide_auto_16_9": "9A",
            "pan_scan_4_3": "3P",
            "letterbox_4_3": "3L",
        },
        icon="mdi:aspect-ratio",
    ),
    SelectSetting(
        "DVFM",
        "video_tv_system",
        {"ntsc": "NT", "pal": "PL", "multi": "MS"},
        False,
        "mdi:television",
    ),
    SelectSetting(
        "DVCS",
        "video_color_space",
        {"rgb_video": "RV", "rgb_pc": "RP", "ycbcr_444": "Y4", "ycbcr_422": "Y2"},
        False,
        "mdi:palette-swatch",
    ),
    SelectSetting(
        "DVDC",
        "video_deep_color",
        {"bit_48": "48", "bit_36": "36", "bit_30": "30", "off": "OF"},
        False,
        "mdi:palette-swatch-variant",
    ),
    SelectSetting(
        "DVHA",
        "audio_hdmi_format",
        {"stereo": "ST", "lpcm": "LP", "bitstream": "BS"},
        icon="mdi:surround-sound",
    ),
    SelectSetting(
        "DVDO",
        "audio_coaxial_output",
        {"lpcm_48k": "48", "lpcm_96k": "96", "lpcm_192k": "19", "bitstream": "BS"},
        False,
        "mdi:audio-input-rca",
    ),
    SelectSetting(
        "DVDR",
        "audio_dynamic_range",
        {"auto": "AT", "on": "00", "off": "01"},
        False,
        "mdi:tune-vertical",
    ),
    SelectSetting(
        "DVSCCh",
        "audio_speaker_configuration",
        {
            "lt_rt": "LR",
            "stereo": "ST",
            "ch_2_1": "21",
            "ch_3_1": "31",
            "ch_5_1": "51",
            "ch_7_1": "71",
        },
        False,
        "mdi:speaker-multiple",
    ),
    SelectSetting(
        "PCTMD",
        "system_time_display",
        {
            "track_elapsed": "EL",
            "track_remaining": "RM",
            "total_elapsed": "TL",
            "total_remaining": "TR",
        },
        icon="mdi:timer-outline",
    ),
    SelectSetting(
        "DVRC",
        "system_remote_code",
        {"code_1": "C1", "code_2": "C2", "code_3": "C3"},
        False,
        "mdi:remote",
    ),
)

SWITCHES: tuple[SwitchSetting, ...] = (
    SwitchSetting("PCAP", "system_auto_play", "00", "01", icon="mdi:play-circle-outline"),
    SwitchSetting("PCAR", "system_auto_resume", "00", "01", icon="mdi:play-pause"),
    SwitchSetting("DVHOSD", "system_on_screen_display", "01", "00", icon="mdi:subtitles-outline"),
    SwitchSetting("PCIRLK", "system_ir_remote_sensor", "01", "00", False, "mdi:remote"),
    SwitchSetting("DVHDC", "system_hdmi_cec", "H1", "OF", False, "mdi:hdmi-port"),
    SwitchSetting("PCPMP", "system_program_mode", "00", "01", False, "mdi:playlist-play"),
    SwitchSetting("DV1K24", "video_1080p24_conversion", "00", "01", icon="mdi:filmstrip"),
    SwitchSetting("DV3D", "video_3d_output", "AT", "01", False, "mdi:video-3d"),
    SwitchSetting(
        "DVPIP", "video_pip_mark", "00", "01", False, "mdi:picture-in-picture-bottom-right"
    ),
    SwitchSetting("DVSA", "audio_secondary_audio_mark", "00", "01", False, "mdi:account-voice"),
)

BUTTONS: tuple[ButtonCommand, ...] = (
    ButtonCommand("disc_eject", "PCDTRYOP", icon="mdi:eject"),
    ButtonCommand("disc_close_tray", "PCDTRYCL", icon="mdi:tray-arrow-down"),
    ButtonCommand("menu_home", "PCHM", icon="mdi:home"),
    ButtonCommand("menu_top", "DVTP", icon="mdi:menu"),
    ButtonCommand("menu_popup", "DVPU", icon="mdi:menu-open"),
    ButtonCommand("menu_option", "DVOP", icon="mdi:dots-horizontal-circle-outline"),
    ButtonCommand("menu_setup", "PCSU", icon="mdi:cog"),
    ButtonCommand("menu_return", "PCRTN", icon="mdi:keyboard-return"),
    ButtonCommand("navigation_up", "PCCUSR3", icon="mdi:chevron-up"),
    ButtonCommand("navigation_down", "PCCUSR4", icon="mdi:chevron-down"),
    ButtonCommand("navigation_left", "PCCUSR1", icon="mdi:chevron-left"),
    ButtonCommand("navigation_right", "PCCUSR2", icon="mdi:chevron-right"),
    ButtonCommand("navigation_enter", "PCENTR", icon="mdi:checkbox-blank-circle-outline"),
    ButtonCommand("playback_audio_primary", "DVADLG+", icon="mdi:account-voice"),
    ButtonCommand("playback_audio_secondary", "DVADLG-", False, "mdi:account-voice"),
    ButtonCommand("playback_subtitle", "DVSBTL1", icon="mdi:subtitles"),
    ButtonCommand("playback_angle", "DVANGL+", False, "mdi:camera-switch"),
    ButtonCommand("playback_next_title", "PCGPNX", False, "mdi:skip-next-circle-outline"),
    ButtonCommand("playback_previous_title", "PCGPPV", False, "mdi:skip-previous-circle-outline"),
    ButtonCommand("playback_pip_mode", "DVMO", False, "mdi:picture-in-picture-top-right"),
    ButtonCommand("playback_display_info", "DVDSIF", False, "mdi:information-outline"),
    ButtonCommand("color_red", "DVFCLR1", False, "mdi:circle"),
    ButtonCommand("color_green", "DVFCLR2", False, "mdi:circle"),
    ButtonCommand("color_blue", "DVFCLR3", False, "mdi:circle"),
    ButtonCommand("color_yellow", "DVFCLR4", False, "mdi:circle"),
    ButtonCommand("system_panel_lock", "23KL", False, "mdi:lock"),
    ButtonCommand("system_panel_unlock", "23KU", False, "mdi:lock-open-variant"),
)

# Status requests used to discover which settings the player can report.
OPTIONAL_CODES: tuple[str, ...] = (
    CAP_MUTE,
    *(n.code for n in NUMBERS),
    *(s.code for s in SELECTS),
    *(s.code for s in SWITCHES),
)
