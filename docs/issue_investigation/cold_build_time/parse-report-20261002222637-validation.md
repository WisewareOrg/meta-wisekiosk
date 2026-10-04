# Buildstats report: wisekiosk-pipeline-tree/build/tmp-raspberrypi0-wifi/buildstats/20261002222637

Real (non-setscene) task files parsed: 3990
Setscene task files (excluded): 90
Unparsed/skipped files: 0
Wall time (first task Started -> last task Ended): 9h44m49s (35089.3s)
Cold full build (first task Started -> do_image_complete Ended): 9h44m49s (35088.6s)
WebKit rebuild (webkitgtk3 do_configure Started -> do_image_complete Ended): 6h17m16s (22636.3s)

build_stats (run-root summary file):
```
Host Info: Linux dad1a3a1c20e 6.18.33.2-microsoft-standard-WSL2 #1 SMP PREEMPT_DYNAMIC Thu Jun 18 21:54:43 UTC 2026 x86_64 
Build Started: 1790980001.36 
Uncompressed Rootfs size: 270M	/work/build/tmp-raspberrypi0-wifi/work/raspberrypi0_wifi-poky-linux-gnueabi/core-image-base/1.0/rootfs
Elapsed time: 35163.16 seconds 
CPU usage: 49.7%
```

## Top 25 recipes by summed real-task elapsed time

| # | recipe | summed elapsed | real tasks | share of wall |
|---|---|---|---|---|
| 1 | webkitgtk3-2.44.3-r0 | 6h14m40s (22480s) | 12 | 64.1% |
| 2 | rust-llvm-native-1.75.0-r0 | 3h16m17s (11777s) | 12 | 33.6% |
| 3 | linux-raspberrypi-1_6.12.93+git-r0 | 2h16m54s (8214s) | 22 | 23.4% |
| 4 | rust-native-1.75.0-r0 | 1h11m41s (4301s) | 9 | 12.3% |
| 5 | glibc-locale-2.39+git-r0 | 0h43m08s (2588s) | 9 | 7.4% |
| 6 | perl-5.38.4-r0 | 0h35m34s (2134s) | 17 | 6.1% |
| 7 | qemu-native-8.2.7-r0 | 0h28m49s (1729s) | 8 | 4.9% |
| 8 | systemd-1_255.22-r0 | 0h26m56s (1616s) | 20 | 4.6% |
| 9 | mesa-2_24.0.7-r0 | 0h25m49s (1549s) | 12 | 4.4% |
| 10 | gcc-runtime-13.5.0-r0 | 0h24m23s (1463s) | 15 | 4.2% |
| 11 | python3-3.12.14-r0 | 0h24m10s (1450s) | 18 | 4.1% |
| 12 | icu-74-2-r0 | 0h22m41s (1361s) | 13 | 3.9% |
| 13 | cmake-native-3.28.3-r0 | 0h21m36s (1296s) | 11 | 3.7% |
| 14 | go-runtime-1.27.1-r0 | 0h19m41s (1181s) | 15 | 3.4% |
| 15 | gtk+3-3.24.41-r0 | 0h19m16s (1156s) | 12 | 3.3% |
| 16 | gcc-cross-arm-13.5.0-r0 | 0h19m02s (1142s) | 12 | 3.3% |
| 17 | openssl-3.5.8-r0 | 0h18m56s (1136s) | 18 | 3.2% |
| 18 | glibc-2.39+git-r1 | 0h17m52s (1072s) | 19 | 3.1% |
| 19 | harfbuzz-8.3.0-r0 | 0h15m43s (943s) | 12 | 2.7% |
| 20 | gstreamer1.0-plugins-base-1.22.12-r0 | 0h14m43s (883s) | 12 | 2.5% |
| 21 | util-linux-2.39.3-r0 | 0h14m34s (874s) | 18 | 2.5% |
| 22 | gnutls-3.8.4-r0 | 0h14m01s (841s) | 18 | 2.4% |
| 23 | gnutls-native-3.8.4-r0 | 0h13m59s (839s) | 14 | 2.4% |
| 24 | glib-2.0-1_2.78.6-r0 | 0h13m53s (833s) | 12 | 2.4% |
| 25 | libunistring-1.2-r0 | 0h13m34s (814s) | 12 | 2.3% |

## Top 25 individual tasks by elapsed time

| # | recipe:task | elapsed | ru_maxrss (KB) | child_maxrss (KB) | started (rel to run start) |
|---|---|---|---|---|---|
| 1 | webkitgtk3-2.44.3-r0:do_compile | 6h06m00s (21960s) | 131988 | 4060000 | 3h30m31s |
| 2 | rust-llvm-native-1.75.0-r0:do_compile | 3h11m11s (11471s) | 76516 | 1717420 | 0h35m08s |
| 3 | rust-native-1.75.0-r0:do_install | 1h11m25s (4285s) | 60628 | 1226628 | 3h48m31s |
| 4 | linux-raspberrypi-1_6.12.93+git-r0:do_compile_kernelmodules | 1h06m22s (3982s) | 59324 | 328772 | 3h48m19s |
| 5 | linux-raspberrypi-1_6.12.93+git-r0:do_compile | 0h41m50s (2510s) | 67516 | 261948 | 2h54m09s |
| 6 | glibc-locale-2.39+git-r0:do_package | 0h29m12s (1752s) | 114940 | 191056 | 4h02m05s |
| 7 | qemu-native-8.2.7-r0:do_compile | 0h26m21s (1581s) | 56884 | 513392 | 0h57m41s |
| 8 | mesa-2_24.0.7-r0:do_compile | 0h20m22s (1222s) | 67068 | 452120 | 2h03m17s |
| 9 | gcc-cross-arm-13.5.0-r0:do_compile | 0h18m12s (1092s) | 78616 | 862876 | 0h07m28s |
| 10 | systemd-1_255.22-r0:do_compile | 0h17m48s (1068s) | 67184 | 224100 | 2h03m52s |
| 11 | gcc-runtime-13.5.0-r0:do_compile | 0h16m02s (962s) | 68436 | 491560 | 0h50m15s |
| 12 | icu-74-2-r0:do_compile | 0h15m41s (941s) | 65584 | 197424 | 2h01m27s |
| 13 | openssl-3.5.8-r0:do_compile | 0h14m15s (855s) | 53620 | 134220 | 1h19m37s |
| 14 | harfbuzz-8.3.0-r0:do_compile | 0h12m31s (751s) | 60584 | 1213844 | 2h19m39s |
| 15 | gtk+3-3.24.41-r0:do_compile | 0h12m07s (727s) | 64316 | 333080 | 2h41m46s |
| 16 | cmake-native-3.28.3-r0:do_compile | 0h11m40s (700s) | 75316 | 691252 | 0h22m13s |
| 17 | go-runtime-1.27.1-r0:do_compile | 0h11m34s (694s) | 63248 | 966120 | 3h38m05s |
| 18 | linux-raspberrypi-1_6.12.93+git-r0:do_package | 0h11m30s (690s) | 119308 | 116060 | 4h55m42s |
| 19 | librsvg-native-2.57.1-r0:do_compile | 0h10m41s (641s) | 71168 | 886892 | 5h00m50s |
| 20 | gstreamer1.0-plugins-base-1.22.12-r0:do_compile | 0h10m04s (604s) | 62392 | 262048 | 3h01m51s |
| 21 | perl-5.38.4-r0:do_compile | 0h09m51s (591s) | 45432 | 303684 | 4h31m27s |
| 22 | cmake-native-3.28.3-r0:do_configure | 0h09m34s (574s) | 81004 | 614168 | 0h12m39s |
| 23 | glibc-2.39+git-r1:do_compile | 0h09m05s (545s) | 110836 | 162080 | 0h27m47s |
| 24 | harfbuzz-native-8.3.0-r0:do_compile | 0h08m49s (529s) | 52100 | 920116 | 3h07m28s |
| 25 | glibc-locale-2.39+git-r0:do_package_write_ipk | 0h07m54s (474s) | 77732 | 228452 | 5h05m08s |

## Concurrency per 10-minute bucket

| bucket (offset from run start) | distinct tasks touching window | point-sample concurrency (threads busy) | sample tasks touching window |
|---|---|---|---|
| 0h00m00s-0h10m00s | 708 | 1 | alsa-lib-1.2.11-r0:do_deploy_source_date_epoch, alsa-lib-1.2.11-r0:do_fetch, alsa-lib-1.2.11-r0:do_patch, alsa-lib-1.2.11-r0:do_populate_lic |
| 0h10m00s-0h20m00s | 81 | 4 | binutils-cross-arm-2.42-r0:do_create_runtime_spdx, bmaptool-native-3.8.0+git-r0:do_create_runtime_spdx, btrfs-tools-native-6.7.1-r0:do_create_runtime_spdx, ca-certificates-native-20260816-r0:do_compile |
| 0h20m00s-0h30m00s | 19 | 3 | cmake-native-3.28.3-r0:do_compile, cmake-native-3.28.3-r0:do_configure, gcc-cross-arm-13.5.0-r0:do_compile, gcc-cross-arm-13.5.0-r0:do_gcc_stash_builddir |
| 0h30m00s-0h40m00s | 32 | 2 | cmake-native-3.28.3-r0:do_compile, cmake-native-3.28.3-r0:do_install, cmake-native-3.28.3-r0:do_populate_sysroot, expat-native-2.6.4-r0:do_compile |
| 0h40m00s-0h50m00s | 106 | 3 | e2fsprogs-native-1.47.0-r0:do_compile, e2fsprogs-native-1.47.0-r0:do_configure, e2fsprogs-native-1.47.0-r0:do_prepare_recipe_sysroot, gcc-runtime-13.5.0-r0:do_configure |
| 0h50m00s-1h00m00s | 86 | 6 | docbook-xml-dtd4-native-4.5-r0:do_compile, docbook-xml-dtd4-native-4.5-r0:do_configure, docbook-xml-dtd4-native-4.5-r0:do_install, docbook-xml-dtd4-native-4.5-r0:do_populate_sysroot |
| 1h00m00s-1h10m00s | 104 | 4 | elfutils-native-0.191-r0:do_compile, elfutils-native-0.191-r0:do_configure, elfutils-native-0.191-r0:do_prepare_recipe_sysroot, expat-2.6.4-r0:do_compile |
| 1h10m00s-1h20m00s | 111 | 5 | bash-completion-2.12.0-r0:do_compile, bash-completion-2.12.0-r0:do_configure, bash-completion-2.12.0-r0:do_install, bash-completion-2.12.0-r0:do_populate_sysroot |
| 1h20m00s-1h30m00s | 58 | 5 | bash-completion-2.12.0-r0:do_package, expat-2.6.4-r0:do_populate_sysroot, gdbm-1.23-r0:do_configure, gdbm-1.23-r0:do_prepare_recipe_sysroot |
| 1h30m00s-1h40m00s | 78 | 6 | attr-2.5.1-r0:do_compile, attr-2.5.1-r0:do_configure, attr-2.5.1-r0:do_install, attr-2.5.1-r0:do_prepare_recipe_sysroot |
| 1h40m00s-1h50m00s | 109 | 6 | acl-2.3.2-r0:do_compile, acl-2.3.2-r0:do_configure, acl-2.3.2-r0:do_install, acl-2.3.2-r0:do_prepare_recipe_sysroot |
| 1h50m00s-2h00m00s | 118 | 5 | acl-2.3.2-r0:do_populate_sysroot, base-files-3.0.14-r0:do_package, base-passwd-3.6.8-r0:do_package, base-passwd-3.6.8-r0:do_packagedata |
| 2h00m00s-2h10m00s | 102 | 5 | acl-2.3.2-r0:do_package, acl-2.3.2-r0:do_packagedata, bzip2-1.0.8-r0:do_collect_spdx_deps, bzip2-1.0.8-r0:do_create_spdx |
| 2h10m00s-2h20m00s | 62 | 6 | encodings-1_1.0.7-r0:do_compile, encodings-1_1.0.7-r0:do_configure, encodings-1_1.0.7-r0:do_install, encodings-1_1.0.7-r0:do_prepare_recipe_sysroot |
| 2h20m00s-2h30m00s | 57 | 6 | at-spi2-core-2.50.1-r0:do_configure, at-spi2-core-2.50.1-r0:do_prepare_recipe_sysroot, dbus-1.14.10-r0:do_compile, dbus-1.14.10-r0:do_configure |
| 2h30m00s-2h40m00s | 99 | 6 | at-spi2-core-2.50.1-r0:do_compile, at-spi2-core-2.50.1-r0:do_configure, at-spi2-core-2.50.1-r0:do_install, at-spi2-core-2.50.1-r0:do_populate_sysroot |
| 2h40m00s-2h50m00s | 83 | 6 | alsa-lib-1.2.11-r0:do_configure, alsa-lib-1.2.11-r0:do_prepare_recipe_sysroot, at-spi2-core-2.50.1-r0:do_package, at-spi2-core-2.50.1-r0:do_packagedata |
| 2h50m00s-3h00m00s | 133 | 6 | acl-2.3.2-r0:do_collect_spdx_deps, acl-2.3.2-r0:do_create_spdx, alsa-lib-1.2.11-r0:do_compile, alsa-lib-1.2.11-r0:do_configure |
| 3h00m00s-3h10m00s | 60 | 6 | desktop-file-utils-0.27-r0:do_compile, desktop-file-utils-0.27-r0:do_install, e2fsprogs-1.47.0-r0:do_configure, e2fsprogs-1.47.0-r0:do_prepare_recipe_sysroot |
| 3h10m00s-3h20m00s | 106 | 6 | alsa-lib-1.2.11-r0:do_package, alsa-lib-1.2.11-r0:do_packagedata, at-spi2-core-native-2.50.1-r0:do_configure, at-spi2-core-native-2.50.1-r0:do_prepare_recipe_sysroot |
| 3h20m00s-3h30m00s | 92 | 6 | at-spi2-core-native-2.50.1-r0:do_compile, at-spi2-core-native-2.50.1-r0:do_configure, at-spi2-core-native-2.50.1-r0:do_install, at-spi2-core-native-2.50.1-r0:do_populate_sysroot |
| 3h30m00s-3h40m00s | 77 | 5 | bash-5.2.21-r0:do_compile, bash-5.2.21-r0:do_configure, bash-5.2.21-r0:do_install, bash-5.2.21-r0:do_package |
| 3h40m00s-3h50m00s | 72 | 5 | at-spi2-core-2.50.1-r0:do_collect_spdx_deps, at-spi2-core-2.50.1-r0:do_create_spdx, avahi-0.8-r0:do_package, avahi-0.8-r0:do_packagedata |
| 3h50m00s-4h00m00s | 102 | 6 | busybox-1.36.1-r0:do_compile, busybox-1.36.1-r0:do_configure, busybox-1.36.1-r0:do_install, busybox-1.36.1-r0:do_package |
| 4h00m00s-4h10m00s | 57 | 6 | avahi-0.8-r0:do_populate_sysroot, busybox-1.36.1-r0:do_packagedata, coreutils-9.4-r0:do_compile, coreutils-9.4-r0:do_configure |
| 4h10m00s-4h20m00s | 43 | 6 | findutils-4.9.0-r0:do_configure, findutils-4.9.0-r0:do_prepare_recipe_sysroot, glib-networking-2.78.1-r0:do_configure, glib-networking-2.78.1-r0:do_prepare_recipe_sysroot |
| 4h20m00s-4h30m00s | 30 | 6 | findutils-4.9.0-r0:do_compile, findutils-4.9.0-r0:do_configure, glib-networking-2.78.1-r0:do_compile, glibc-locale-2.39+git-r0:do_package |
| 4h30m00s-4h40m00s | 65 | 6 | alsa-topology-conf-1.2.5.1-r0:do_package, alsa-ucm-conf-1.2.11-r0:do_package, casync-2+git-r0:do_prepare_recipe_sysroot, fftw-3.3.10-r0:do_populate_sysroot |
| 4h40m00s-4h50m00s | 68 | 6 | casync-2+git-r0:do_compile, casync-2+git-r0:do_configure, casync-2+git-r0:do_install, casync-2+git-r0:do_package |
| 4h50m00s-5h00m00s | 126 | 6 | bash-5.2.21-r0:do_collect_spdx_deps, bash-5.2.21-r0:do_create_spdx, brotli-1.1.0-r0:do_collect_spdx_deps, coreutils-9.4-r0:do_packagedata |
| 5h00m00s-5h10m00s | 390 | 4 | adwaita-icon-theme-45.0-r0:do_collect_spdx_deps, alsa-lib-1.2.11-r0:do_collect_spdx_deps, alsa-lib-1.2.11-r0:do_create_spdx, alsa-topology-conf-1.2.5.1-r0:do_package_qa |
| 5h10m00s-5h20m00s | 361 | 6 | adwaita-icon-theme-45.0-r0:do_compile, adwaita-icon-theme-45.0-r0:do_configure, adwaita-icon-theme-45.0-r0:do_create_runtime_spdx, adwaita-icon-theme-45.0-r0:do_create_spdx |
| 5h20m00s-5h30m00s | 330 | 6 | acl-2.3.2-r0:do_create_runtime_spdx, acl-2.3.2-r0:do_package_qa, acl-2.3.2-r0:do_package_write_ipk, avahi-0.8-r0:do_create_runtime_spdx |
| 5h30m00s-5h40m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 5h40m00s-5h50m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 5h50m00s-6h00m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 6h00m00s-6h10m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 6h10m00s-6h20m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 6h20m00s-6h30m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 6h30m00s-6h40m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 6h40m00s-6h50m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 6h50m00s-7h00m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 7h00m00s-7h10m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 7h10m00s-7h20m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 7h20m00s-7h30m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 7h30m00s-7h40m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 7h40m00s-7h50m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 7h50m00s-8h00m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 8h00m00s-8h10m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 8h10m00s-8h20m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 8h20m00s-8h30m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 8h30m00s-8h40m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 8h40m00s-8h50m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 8h50m00s-9h00m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 9h00m00s-9h10m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 9h10m00s-9h20m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 9h20m00s-9h30m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 9h30m00s-9h40m00s | 14 | 1 | surf-2.1-r0:do_compile, surf-2.1-r0:do_configure, surf-2.1-r0:do_install, surf-2.1-r0:do_package |
| 9h40m00s-9h50m00s | 25 | 3 | core-image-base-1.0-r0:do_create_runtime_spdx, core-image-base-1.0-r0:do_flush_pseudodb, core-image-base-1.0-r0:do_image, core-image-base-1.0-r0:do_image_complete |

## Latest-finishing tasks (top 20 by Ended time) -- tail of the critical path

| # | recipe:task | ended (rel to run start) | started (rel) | elapsed | concurrently running at its start |
|---|---|---|---|---|---|
| 1 | core-image-base-1.0-r0:do_populate_lic_deploy | 9h44m49s | 9h44m49s | 0h00m00s | 0:  |
| 2 | core-image-base-1.0-r0:do_image_complete | 9h44m49s | 9h44m39s | 0h00m10s | 0:  |
| 3 | core-image-base-1.0-r0:do_image_wic | 9h44m38s | 9h43m54s | 0h00m45s | 2: core-image-base-1.0-r0:do_image_ext3, core-image-base-1.0-r0:do_image_ext4 |
| 4 | core-image-base-1.0-r0:do_image_ext3 | 9h44m12s | 9h43m53s | 0h00m19s | 1: core-image-base-1.0-r0:do_image_ext4 |
| 5 | core-image-base-1.0-r0:do_image_ext4 | 9h44m11s | 9h43m53s | 0h00m18s | 0:  |
| 6 | core-image-base-1.0-r0:do_image_tar | 9h44m10s | 9h43m54s | 0h00m16s | 3: core-image-base-1.0-r0:do_image_ext3, core-image-base-1.0-r0:do_image_ext4, core-image-base-1.0-r0:do_image_wic |
| 7 | core-image-base-1.0-r0:do_rootfs_wicenv | 9h43m52s | 9h43m52s | 0h00m00s | 0:  |
| 8 | core-image-base-1.0-r0:do_write_wks_template | 9h43m52s | 9h43m52s | 0h00m00s | 0:  |
| 9 | core-image-base-1.0-r0:do_image | 9h43m51s | 9h43m45s | 0h00m06s | 0:  |
| 10 | core-image-base-1.0-r0:do_image_qa | 9h43m44s | 9h43m44s | 0h00m00s | 0:  |
| 11 | core-image-base-1.0-r0:do_flush_pseudodb | 9h43m43s | 9h43m43s | 0h00m00s | 0:  |
| 12 | core-image-base-1.0-r0:do_rootfs | 9h43m41s | 9h40m38s | 0h03m02s | 0:  |
| 13 | webkitgtk3-2.44.3-r0:do_package_qa | 9h40m37s | 9h39m40s | 0h00m57s | 3: surf-2.1-r0:do_package, webkitgtk3-2.44.3-r0:do_create_spdx, webkitgtk3-2.44.3-r0:do_package_write_ipk |
| 14 | core-image-base-1.0-r0:do_create_runtime_spdx | 9h40m13s | 9h40m10s | 0h00m02s | 3: kiosk-session-1.0-r0:do_create_runtime_spdx, surf-2.1-r0:do_create_runtime_spdx, webkitgtk3-2.44.3-r0:do_package_qa |
| 15 | surf-2.1-r0:do_create_runtime_spdx | 9h40m10s | 9h40m10s | 0h00m00s | 2: kiosk-session-1.0-r0:do_create_runtime_spdx, webkitgtk3-2.44.3-r0:do_package_qa |
| 16 | kiosk-session-1.0-r0:do_create_runtime_spdx | 9h40m10s | 9h40m10s | 0h00m00s | 1: webkitgtk3-2.44.3-r0:do_package_qa |
| 17 | webkitgtk3-2.44.3-r0:do_create_runtime_spdx | 9h40m10s | 9h40m08s | 0h00m01s | 2: surf-2.1-r0:do_collect_spdx_deps, webkitgtk3-2.44.3-r0:do_package_qa |
| 18 | surf-2.1-r0:do_create_spdx | 9h40m09s | 9h40m09s | 0h00m00s | 2: webkitgtk3-2.44.3-r0:do_create_runtime_spdx, webkitgtk3-2.44.3-r0:do_package_qa |
| 19 | surf-2.1-r0:do_collect_spdx_deps | 9h40m09s | 9h40m08s | 0h00m01s | 1: webkitgtk3-2.44.3-r0:do_package_qa |
| 20 | webkitgtk3-2.44.3-r0:do_create_spdx | 9h40m08s | 9h39m39s | 0h00m29s | 0:  |

Max point-sample concurrency (threads busy) in this run: 6
Mean point-sample concurrency (over non-idle buckets): 3.4
Buckets with exactly 1 task in flight (single-threaded tail): 26 of 60 (260 min)
Buckets with 0 tasks in flight (dead time / bitbake overhead only): 1

