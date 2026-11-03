# NESTang v0.4 Dock overlay

Apply on top of the `retro/nestang` submodule (tag v0.4). Do not vendor NESTang.

```sh
# from repo root, after git submodule update --init
git -C retro/nestang apply ../overlay/nestang_dock.cst.patch
cd retro/nestang
QT_QPA_PLATFORM=xcb gw_sh ../overlay/build_dock.tcl
```

What it changes in `src/nestang_dock.cst`:

- `sys_resetn` T2: `IO_TYPE=LVCMOS15 PULL_MODE=UP` (was `PULL_MODE=NONE`)
- `d7` D7: `IO_TYPE=LVCMOS15 PULL_MODE=UP`
- `DDR3_nCS` P5 SSTL15 added

The submodule itself stays clean at v0.4; this patch is the only local HDL delta.
