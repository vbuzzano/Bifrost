# ApolloDevBox - Setup System Roadmap

## 🎯 Current Status: MVP Functional

**Version**: 0.1.0  
**Date**: 1 December 2025  
**Status**: ⚠️ Basic functionality, missing features

---

## 🐛 Bugs to Fix

### B1: `install` doesn't re-check configuration
- **Current**: Skips packages already in state.json
- **Expected**: Always ask project name, description, then propose reinstall for each package
- **Choices**: Skip | Reinstall | Manual

### B2: File tracking incomplete
- **Current**: Tracks directories, not individual files
- **Problem**: `INC:**/newmouse.h:include/libraries/newmouse.h` copies to existing dir, not tracked
- **Impact**: `uninstall` doesn't remove these files

### B3: Config changes not detected
- **Current**: No comparison between config and state
- **Problem**: Changing destination in config doesn't trigger reinstall
- **Impact**: Old files remain, new files added = duplicates

### B4: `include/` directory not cleaned
- **Current**: Only `build/`, `dist/`, `vendor/` are removed on uninstall
- **Problem**: Files copied to `include/` (like newmouse.h) remain

---

## ❌ Missing Features

### F1: `pkg update` command
- **Expected**: Re-check all packages, propose Skip/Reinstall/Manual for each
- **Current**: Command doesn't exist

### F2: `pkg reinstall <name>` command
- **Expected**: Reinstall specific package by name
- **Current**: Must uninstall everything

### F3: `uninstall` cache option
- **Expected**: `.\setup.ps1 uninstall` keeps cache, `.\setup.ps1 uninstall -Purge` removes cache
- **Current**: Always removes `.setup/cache/`
- **Benefit**: Faster reinstall (no re-download)

### F4: "All" option for Y/n prompts
- **Expected**: Add `[A]ll` option to install all remaining packages without prompting
- **Current**: Must answer Y/n for each package individually
- **Prompt**: `Install? [Y]es [N]o [A]ll [a]:`

### F5: Individual file tracking
- **Expected**: Track every file copied, not just root directories
- **State format**:
```json
{
  "packages": {
    "NewMouse": {
      "installed": true,
      "files": [
        "include/libraries/newmouse.h"
      ],
      "createdDirs": [
        "include/libraries"
      ]
    }
  }
}
```

### F6: Config hash comparison
- **Expected**: Store hash of Extract rules in state
- **On install**: Compare current config vs stored hash
- **If different**: Force reinstall prompt for that package

### F7: Interactive install flow
```
=== ApolloDevBox Setup ===

Project name [ApolloFreeWheel]: 
Description [FreeWheel for Vampire]: 

=== Packages ===

[1/8] VBCC Compiler (installed)
  [S]kip  [R]einstall  [M]anual  [s]: 

[2/8] NDK 3.2 (not installed)
  [I]nstall  [S]kip  [M]anual  [i]: 
```

### F8: Differentiate created vs existing directories
- Track if we created a directory or if it existed
- Only delete directories we created
- For existing dirs: only delete files we added

---

## 📋 Implementation Plan

### Phase 1: Fix Core Issues
1. [ ] B4: Add `include/` to uninstall cleanup
2. [ ] B2: Track individual files in state.json
3. [ ] B1: Rework install flow with interactive prompts
4. [ ] F3: Uninstall keeps cache by default, -Purge to remove
5. [ ] F4: Add "All" option to Y/n prompts

### Phase 2: Package Commands
1. [ ] F1: Implement `pkg update`
2. [ ] F2: Implement `pkg reinstall <name>`
3. [ ] F6: Add config hash to state

### Phase 3: Polish
1. [ ] F7: Better interactive prompts
2. [ ] F8: Track created vs existing directories
3. [ ] Documentation

---

## 🔮 Future: Standalone Project

**Location**: `E:\Projects\amiga-projects\ApolloDevBox`

When extracted to standalone project:
- Generic template for any Amiga cross-compilation project
- `apollodevbox init` to scaffold new project
- Shared config between MouseMaster, ApolloFreeWheel, etc.

---

## 📝 Notes

### State.json Structure (Target)
```json
{
  "version": "0.1.0",
  "configHash": "abc123",
  "project": {
    "name": "ApolloFreeWheel",
    "description": "FreeWheel for Vampire"
  },
  "packages": {
    "NewMouse": {
      "installed": true,
      "configHash": "def456",
      "files": [
        "include/libraries/newmouse.h"
      ],
      "createdDirs": [],
      "existingDirs": [
        "include/libraries"
      ]
    }
  }
}
```

### Extract Types Behavior
| Type | Typical Destination | Track Files? | Delete Dir? |
|------|---------------------|--------------|-------------|
| SDK | `sdk/NDK_3.2/` | Dir only | Yes (we create) |
| SRC | `vendor/freewheel/` | Dir only | Yes (we create) |
| INC | `include/libraries/file.h` | Each file | No (existing) |
| TOOL | `tools/vbcc/` | Dir only | Yes (we create) |
