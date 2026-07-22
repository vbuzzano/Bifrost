# ============================================================================
# AmigaDevBox - User Configuration
# ============================================================================
# This file contains user-specific and project settings.
# Customize as needed. Values here override .setup/config.psd1
# ============================================================================

@{
    # ========================================================================
    # Project Settings
    # ========================================================================
    Project = @{
        Name        = "Bifrost"
        Version     = "0.4.1"
        VersionDate = "22.07.2026"
        Author      = "Vincent Buzzano"
        Description = "Amiga Mouse and Keyboard Input Controller via PC (Windows/Mac/Linux)"
        DescShort   = "Amiga Mouse & Keyboard Controller"
    }

    # ========================================================================
    # Cache Path Override (optional)
    # ========================================================================
    # Uncomment to use a custom cache directory for downloads
    # Useful to share downloads between projects or use a faster drive
    # ========================================================================
    # CachePath = "D:/Downloads/amiga-cache"

    # ========================================================================
    # Custom Environment Variables (added to .env)
    # ========================================================================
    Envs = @{
        APOLLO_V4_HOST      = "10.0.0.158:Ram Disk"
        INSTALL_FILE        = "Install"
        GUIDE_FILE          = "Bifrost.guide"
        README_FILE         = "Bifrost.readme"
        ASSETS_DIR          = ".\assets"
    }

    # ========================================================================
    # Additional Packages - Add your custom packages here
    # ========================================================================
    # Format: TYPE:pattern:destination[:ENV_VAR]
    # Types: SDK, SRC, INC, TOOL, LIB, FILE
    #
    # Examples:
    # - "SDK:MySDK/*:sdk/mysdk:MYSDK_PATH"     → SDK with env var
    # - "SRC:src/*:src"                        → Source files
    # - "INC:include/*:include"                → Include files
    # - "TOOL:bin/*:tools"                     → Tools/binaries
    # - "LIB:libs/*.lib:lib"                   → Libraries
    # - "FILE:readme.txt:docs"                 → Single file
    # ========================================================================
    Packages = @(
        # Example package:
        # @{
        #     Name        = "MyLibrary"
        #     Url         = "https://example.com/mylib.lha"
        #     File        = "mylib.lha"
        #     Description = "My custom library"
        #     Archive     = "lha"           # zip, lha, 7z, tar.gz
        #     Mode        = "auto"          # auto = install without asking
        #     Extract     = @(
        #         "LIB:mylib/*:vendor/mylib:MYLIB_PATH"
        #     )
        # }
        @{
            Name        = "NewMouse"
            Url         = "https://aminet.net/driver/input/NewMouse12.lha"
            File        = "NewMouse12.lha"
            Description = "NewMouse 1.2 header files"
            Archive     = "lha"
            Mode        = "auto"
            Extract     = @(
                "INC:**/newmouse.h:vendor/newmouse:NEWMOUSE_INC"
            )
        }
    )

    # ========================================================================
    # Build Settings
    # ========================================================================
    Build = @{
        EXE_NAME = "Bifrost"

        # Default CPU target (68000, 68020, 68040, 68080)
        DefaultCPU  = "68020"

        # Default FPU (empty, 68020, 68040, 68080)
        #DefaultFPU  = "68080"
    }
}

