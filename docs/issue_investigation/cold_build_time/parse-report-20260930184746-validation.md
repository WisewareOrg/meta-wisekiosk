# Buildstats report: wisekiosk-pipeline-tree/build/tmp-raspberrypi0-wifi/buildstats/20260930184746

Real (non-setscene) task files parsed: 4980
Setscene task files (excluded): 1493
Unparsed/skipped files: 0
Wall time (first task Started -> last task Ended): 8h18m42s (29921.9s)
Cold full build (first task Started -> do_image_complete Ended): 8h18m41s (29921.0s)
WebKit rebuild (webkitgtk3 do_configure Started -> do_image_complete Ended): 5h01m33s (18093.2s)

build_stats (run-root summary file):
```
Host Info: Linux 99f9f52af544 6.18.33.2-microsoft-standard-WSL2 #1 SMP PREEMPT_DYNAMIC Thu Jun 18 21:54:43 UTC 2026 x86_64 
Build Started: 1790794072.08 
Uncompressed Rootfs size: 269M	/work/build/tmp-raspberrypi0-wifi/work/raspberrypi0_wifi-poky-linux-gnueabi/core-image-base/1.0/rootfs
Elapsed time: 30110.32 seconds 
CPU usage: 46.1%
```

## Top 25 recipes by summed real-task elapsed time

| # | recipe | summed elapsed | real tasks | share of wall |
|---|---|---|---|---|
| 1 | webkitgtk3-2.44.3-r0 | 4h58m01s (17881s) | 16 | 59.8% |
| 2 | linux-raspberrypi-1_6.12.93+git-r0 | 2h18m00s (8280s) | 33 | 27.7% |
| 3 | rust-native-1.75.0-r0 | 1h42m39s (6159s) | 14 | 20.6% |
| 4 | icu-74-2-r0 | 0h40m16s (2416s) | 19 | 8.1% |
| 5 | gcc-cross-arm-13.4.0-r0 | 0h32m52s (1972s) | 9 | 6.6% |
| 6 | glibc-locale-2.39+git-r0 | 0h32m28s (1948s) | 9 | 6.5% |
| 7 | glibc-2.39+git-r1 | 0h27m49s (1669s) | 16 | 5.6% |
| 8 | qemu-native-8.2.7-r0 | 0h25m26s (1526s) | 11 | 5.1% |
| 9 | python3-3.12.13-r0 | 0h23m39s (1419s) | 18 | 4.7% |
| 10 | cargo-native-1.75.0-r0 | 0h23m07s (1387s) | 14 | 4.6% |
| 11 | perl-5.38.4-r0 | 0h22m30s (1350s) | 14 | 4.5% |
| 12 | go-runtime-1.26.7-r0 | 0h20m20s (1220s) | 15 | 4.1% |
| 13 | systemd-1_255.21-r0 | 0h18m35s (1115s) | 17 | 3.7% |
| 14 | mesa-2_24.0.7-r0 | 0h17m22s (1042s) | 16 | 3.5% |
| 15 | openssl-3.5.7-r0 | 0h15m53s (953s) | 15 | 3.2% |
| 16 | gnutls-3.8.4-r0 | 0h14m51s (891s) | 18 | 3.0% |
| 17 | gtk+3-3.24.41-r0 | 0h14m45s (885s) | 16 | 3.0% |
| 18 | librsvg-native-2.57.1-r0 | 0h13m24s (804s) | 13 | 2.7% |
| 19 | glib-2.0-1_2.78.6-r0 | 0h13m01s (781s) | 19 | 2.6% |
| 20 | gcc-runtime-13.4.0-r0 | 0h12m38s (758s) | 12 | 2.5% |
| 21 | harfbuzz-8.3.0-r0 | 0h12m35s (755s) | 16 | 2.5% |
| 22 | gstreamer1.0-plugins-base-1.22.12-r0 | 0h12m22s (742s) | 16 | 2.5% |
| 23 | util-linux-2.39.3-r0 | 0h11m57s (717s) | 15 | 2.4% |
| 24 | fftw-3.3.10-r0 | 0h11m13s (673s) | 15 | 2.3% |
| 25 | coreutils-9.4-r0 | 0h10m50s (650s) | 14 | 2.2% |

## Top 25 individual tasks by elapsed time

| # | recipe:task | elapsed | ru_maxrss (KB) | child_maxrss (KB) | started (rel to run start) |
|---|---|---|---|---|---|
| 1 | webkitgtk3-2.44.3-r0:do_compile | 4h48m38s (17318s) | 141760 | 4061156 | 3h19m47s |
| 2 | rust-native-1.75.0-r0:do_install | 1h38m59s (5939s) | 68348 | 1252780 | 0h40m53s |
| 3 | linux-raspberrypi-1_6.12.93+git-r0:do_compile_kernelmodules | 1h08m45s (4125s) | 63888 | 328896 | 1h23m36s |
| 4 | linux-raspberrypi-1_6.12.93+git-r0:do_compile | 0h36m06s (2166s) | 69152 | 262204 | 0h47m19s |
| 5 | gcc-cross-arm-13.4.0-r0:do_compile | 0h31m14s (1874s) | 71188 | 882224 | 0h12m07s |
| 6 | icu-74-2-r0:do_make_icudata | 0h29m43s (1783s) | 56928 | 163452 | 2h14m06s |
| 7 | qemu-native-8.2.7-r0:do_compile | 0h22m53s (1373s) | 71860 | 513464 | 0h20m11s |
| 8 | cargo-native-1.75.0-r0:do_compile | 0h19m44s (1184s) | 60536 | 2242512 | 3h03m30s |
| 9 | glibc-locale-2.39+git-r0:do_package | 0h19m14s (1154s) | 114420 | 190480 | 3h20m46s |
| 10 | glibc-2.39+git-r1:do_compile | 0h18m37s (1117s) | 84500 | 161884 | 0h46m46s |
| 11 | linux-raspberrypi-1_6.12.93+git-r0:do_package | 0h13m47s (827s) | 130896 | 127424 | 3h03m33s |
| 12 | mesa-2_24.0.7-r0:do_compile | 0h12m58s (778s) | 63072 | 452304 | 2h17m48s |
| 13 | systemd-1_255.21-r0:do_compile | 0h12m06s (726s) | 63520 | 235228 | 2h16m51s |
| 14 | go-runtime-1.26.7-r0:do_compile | 0h12m04s (724s) | 59136 | 933112 | 2h51m34s |
| 15 | librsvg-native-2.57.1-r0:do_compile | 0h11m53s (713s) | 64600 | 865240 | 3h24m37s |
| 16 | openssl-3.5.7-r0:do_compile | 0h11m17s (677s) | 62720 | 134336 | 1h37m37s |
| 17 | harfbuzz-8.3.0-r0:do_compile | 0h10m38s (638s) | 60172 | 1213960 | 2h52m42s |
| 18 | gtk+3-3.24.41-r0:do_compile | 0h10m06s (606s) | 68080 | 333172 | 3h06m24s |
| 19 | linux-raspberrypi-1_6.12.93+git-r0:do_package_write_ipk | 0h09m11s (551s) | 93632 | 93632 | 3h48m00s |
| 20 | glibc-locale-2.39+git-r0:do_package_write_ipk | 0h09m06s (546s) | 81664 | 179580 | 3h47m35s |
| 21 | binutils-cross-arm-2.42-r0:do_compile | 0h08m51s (531s) | 70176 | 664384 | 0h02m46s |
| 22 | gstreamer1.0-plugins-base-1.22.12-r0:do_compile | 0h08m26s (506s) | 63628 | 261732 | 3h06m39s |
| 23 | gcc-runtime-13.4.0-r0:do_compile | 0h07m55s (475s) | 70924 | 487420 | 1h18m59s |
| 24 | fftw-3.3.10-r0:do_compile | 0h07m47s (467s) | 58560 | 68840 | 2h53m20s |
| 25 | gtk+3-native-3.24.41-r0:do_compile | 0h07m46s (466s) | 67372 | 320144 | 0h46m54s |

## Concurrency per 10-minute bucket

| bucket (offset from run start) | distinct tasks touching window | point-sample concurrency (threads busy) | sample tasks touching window |
|---|---|---|---|
| 0h00m00s-0h10m00s | 668 | 1 | acl-2.3.2-r0:do_fetch, acl-2.3.2-r0:do_patch, acl-2.3.2-r0:do_unpack, alsa-lib-1.2.11-r0:do_fetch |
| 0h10m00s-0h20m00s | 254 | 5 | alsa-lib-1.2.11-r0:do_patch, alsa-lib-1.2.11-r0:do_unpack, at-spi2-core-2.50.1-r0:do_write_config, base-files-3.0.14-r0:do_populate_sysroot |
| 0h20m00s-0h30m00s | 136 | 6 | desktop-file-utils-0.27-r0:do_fetch, elfutils-native-0.191-r0:do_compile, elfutils-native-0.191-r0:do_configure, elfutils-native-0.191-r0:do_prepare_recipe_sysroot |
| 0h30m00s-0h40m00s | 315 | 4 | at-spi2-core-native-2.50.1-r0:do_fetch, at-spi2-core-native-2.50.1-r0:do_patch, at-spi2-core-native-2.50.1-r0:do_unpack, avahi-0.8-r0:do_fetch |
| 0h40m00s-0h50m00s | 191 | 5 | adwaita-icon-theme-45.0-r0:do_fetch, alsa-topology-conf-1.2.5.1-r0:do_fetch, alsa-ucm-conf-1.2.11-r0:do_fetch, at-spi2-core-native-2.50.1-r0:do_compile |
| 0h50m00s-1h00m00s | 389 | 6 | adwaita-icon-theme-45.0-r0:do_patch, adwaita-icon-theme-45.0-r0:do_unpack, adwaita-icon-theme-45.0-r0:do_write_config, alsa-topology-conf-1.2.5.1-r0:do_compile |
| 1h00m00s-1h10m00s | 409 | 5 | alsa-topology-conf-1.2.5.1-r0:do_collect_spdx_deps, alsa-topology-conf-1.2.5.1-r0:do_create_runtime_spdx, alsa-topology-conf-1.2.5.1-r0:do_create_spdx, alsa-topology-conf-1.2.5.1-r0:do_package_qa |
| 1h10m00s-1h20m00s | 112 | 5 | bc-native-1.07.1-r0:do_create_runtime_spdx, binutils-cross-arm-2.42-r0:do_create_runtime_spdx, bison-native-3.8.2-r0:do_create_runtime_spdx, bmaptool-native-3.8.0+git-r0:do_create_runtime_spdx |
| 1h20m00s-1h30m00s | 60 | 3 | expat-2.6.4-r0:do_compile, expat-2.6.4-r0:do_configure, expat-2.6.4-r0:do_install, expat-2.6.4-r0:do_prepare_recipe_sysroot |
| 1h30m00s-1h40m00s | 94 | 6 | bash-completion-2.12.0-r0:do_compile, bash-completion-2.12.0-r0:do_configure, bash-completion-2.12.0-r0:do_install, bash-completion-2.12.0-r0:do_populate_sysroot |
| 1h40m00s-1h50m00s | 67 | 6 | bash-completion-2.12.0-r0:do_package, bash-completion-2.12.0-r0:do_packagedata, bzip2-1.0.8-r0:do_package, expat-2.6.4-r0:do_populate_sysroot |
| 1h50m00s-2h00m00s | 81 | 6 | attr-2.5.1-r0:do_compile, attr-2.5.1-r0:do_configure, attr-2.5.1-r0:do_install, attr-2.5.1-r0:do_populate_sysroot |
| 2h00m00s-2h10m00s | 100 | 6 | acl-2.3.2-r0:do_compile, acl-2.3.2-r0:do_configure, acl-2.3.2-r0:do_install, acl-2.3.2-r0:do_populate_sysroot |
| 2h10m00s-2h20m00s | 116 | 6 | acl-2.3.2-r0:do_package, acl-2.3.2-r0:do_packagedata, base-passwd-3.6.8-r0:do_packagedata, bzip2-1.0.8-r0:do_collect_spdx_deps |
| 2h20m00s-2h30m00s | 88 | 6 | dbus-1.14.10-r0:do_configure, dbus-1.14.10-r0:do_prepare_recipe_sysroot, expat-2.6.4-r0:do_collect_spdx_deps, expat-2.6.4-r0:do_create_spdx |
| 2h30m00s-2h40m00s | 178 | 6 | alsa-lib-1.2.11-r0:do_compile, alsa-lib-1.2.11-r0:do_configure, alsa-lib-1.2.11-r0:do_install, alsa-lib-1.2.11-r0:do_prepare_recipe_sysroot |
| 2h40m00s-2h50m00s | 252 | 6 | acl-2.3.2-r0:do_collect_spdx_deps, acl-2.3.2-r0:do_create_spdx, alsa-lib-1.2.11-r0:do_install, alsa-lib-1.2.11-r0:do_package |
| 2h50m00s-3h00m00s | 75 | 5 | bash-5.2.21-r0:do_compile, bash-5.2.21-r0:do_install, bash-5.2.21-r0:do_package, e2fsprogs-1.47.0-r0:do_packagedata |
| 3h00m00s-3h10m00s | 126 | 5 | at-spi2-core-2.50.1-r0:do_collect_spdx_deps, at-spi2-core-2.50.1-r0:do_create_spdx, avahi-0.8-r0:do_package, avahi-0.8-r0:do_packagedata |
| 3h10m00s-3h20m00s | 65 | 6 | busybox-1.36.1-r0:do_package, cargo-native-1.75.0-r0:do_compile, coreutils-9.4-r0:do_compile, coreutils-9.4-r0:do_configure |
| 3h20m00s-3h30m00s | 92 | 6 | avahi-0.8-r0:do_populate_sysroot, busybox-1.36.1-r0:do_packagedata, cargo-native-1.75.0-r0:do_compile, cargo-native-1.75.0-r0:do_install |
| 3h30m00s-3h40m00s | 131 | 6 | adwaita-icon-theme-45.0-r0:do_compile, adwaita-icon-theme-45.0-r0:do_configure, adwaita-icon-theme-45.0-r0:do_install, adwaita-icon-theme-45.0-r0:do_package |
| 3h40m00s-3h50m00s | 473 | 6 | adwaita-icon-theme-45.0-r0:do_collect_spdx_deps, adwaita-icon-theme-45.0-r0:do_create_spdx, adwaita-icon-theme-45.0-r0:do_packagedata, alsa-lib-1.2.11-r0:do_collect_spdx_deps |
| 3h50m00s-4h00m00s | 309 | 6 | adwaita-icon-theme-45.0-r0:do_package_qa, adwaita-icon-theme-45.0-r0:do_package_write_ipk, alsa-lib-1.2.11-r0:do_create_runtime_spdx, alsa-lib-1.2.11-r0:do_package_qa |
| 4h00m00s-4h10m00s | 296 | 5 | acl-2.3.2-r0:do_create_runtime_spdx, acl-2.3.2-r0:do_package_qa, acl-2.3.2-r0:do_package_write_ipk, adwaita-icon-theme-45.0-r0:do_create_runtime_spdx |
| 4h10m00s-4h20m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 4h20m00s-4h30m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 4h30m00s-4h40m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 4h40m00s-4h50m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 4h50m00s-5h00m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 5h00m00s-5h10m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 5h10m00s-5h20m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 5h20m00s-5h30m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
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
| 8h00m00s-8h10m00s | 8 | 1 | surf-2.1-r0:do_compile, surf-2.1-r0:do_configure, surf-2.1-r0:do_install, surf-2.1-r0:do_prepare_recipe_sysroot |
| 8h10m00s-8h20m00s | 29 | 1 | core-image-base-1.0-r0:do_create_runtime_spdx, core-image-base-1.0-r0:do_flush_pseudodb, core-image-base-1.0-r0:do_image, core-image-base-1.0-r0:do_image_complete |

## Latest-finishing tasks (top 20 by Ended time) -- tail of the critical path

| # | recipe:task | ended (rel to run start) | started (rel) | elapsed | concurrently running at its start |
|---|---|---|---|---|---|
| 1 | core-image-base-1.0-r0:do_populate_lic_deploy | 8h18m42s | 8h18m42s | 0h00m00s | 0:  |
| 2 | core-image-base-1.0-r0:do_image_complete | 8h18m41s | 8h18m29s | 0h00m12s | 0:  |
| 3 | core-image-base-1.0-r0:do_image_wic | 8h18m28s | 8h17m21s | 0h01m08s | 1: core-image-base-1.0-r0:do_image_ext4 |
| 4 | core-image-base-1.0-r0:do_image_ext3 | 8h17m49s | 8h17m22s | 0h00m28s | 2: core-image-base-1.0-r0:do_image_ext4, core-image-base-1.0-r0:do_image_wic |
| 5 | core-image-base-1.0-r0:do_image_ext4 | 8h17m44s | 8h17m20s | 0h00m24s | 0:  |
| 6 | core-image-base-1.0-r0:do_image_tar | 8h17m43s | 8h17m23s | 0h00m20s | 3: core-image-base-1.0-r0:do_image_ext3, core-image-base-1.0-r0:do_image_ext4, core-image-base-1.0-r0:do_image_wic |
| 7 | core-image-base-1.0-r0:do_rootfs_wicenv | 8h17m19s | 8h17m19s | 0h00m00s | 0:  |
| 8 | core-image-base-1.0-r0:do_write_wks_template | 8h16m54s | 8h16m54s | 0h00m00s | 0:  |
| 9 | core-image-base-1.0-r0:do_image | 8h16m52s | 8h16m45s | 0h00m07s | 0:  |
| 10 | core-image-base-1.0-r0:do_image_qa | 8h16m44s | 8h16m44s | 0h00m00s | 0:  |
| 11 | core-image-base-1.0-r0:do_flush_pseudodb | 8h16m42s | 8h16m42s | 0h00m00s | 0:  |
| 12 | core-image-base-1.0-r0:do_rootfs | 8h16m39s | 8h13m22s | 0h03m17s | 0:  |
| 13 | webkitgtk3-2.44.3-r0:do_package_qa | 8h13m21s | 8h12m19s | 0h01m01s | 3: surf-2.1-r0:do_package, webkitgtk3-2.44.3-r0:do_create_spdx, webkitgtk3-2.44.3-r0:do_package_write_ipk |
| 14 | core-image-base-1.0-r0:do_create_runtime_spdx | 8h12m59s | 8h12m56s | 0h00m02s | 3: kiosk-session-1.0-r0:do_create_runtime_spdx, surf-2.1-r0:do_create_runtime_spdx, webkitgtk3-2.44.3-r0:do_package_qa |
| 15 | surf-2.1-r0:do_create_runtime_spdx | 8h12m57s | 8h12m56s | 0h00m00s | 2: kiosk-session-1.0-r0:do_create_runtime_spdx, webkitgtk3-2.44.3-r0:do_package_qa |
| 16 | kiosk-session-1.0-r0:do_create_runtime_spdx | 8h12m57s | 8h12m56s | 0h00m00s | 1: webkitgtk3-2.44.3-r0:do_package_qa |
| 17 | webkitgtk3-2.44.3-r0:do_create_runtime_spdx | 8h12m55s | 8h12m54s | 0h00m01s | 2: surf-2.1-r0:do_collect_spdx_deps, webkitgtk3-2.44.3-r0:do_package_qa |
| 18 | surf-2.1-r0:do_create_spdx | 8h12m55s | 8h12m55s | 0h00m00s | 2: webkitgtk3-2.44.3-r0:do_create_runtime_spdx, webkitgtk3-2.44.3-r0:do_package_qa |
| 19 | surf-2.1-r0:do_collect_spdx_deps | 8h12m55s | 8h12m54s | 0h00m01s | 1: webkitgtk3-2.44.3-r0:do_package_qa |
| 20 | webkitgtk3-2.44.3-r0:do_create_spdx | 8h12m53s | 8h12m19s | 0h00m34s | 1: surf-2.1-r0:do_package |

Max point-sample concurrency (threads busy) in this run: 6
Mean point-sample concurrency (over non-idle buckets): 3.2
Buckets with exactly 1 task in flight (single-threaded tail): 26 of 51 (260 min)
Buckets with 0 tasks in flight (dead time / bitbake overhead only): 1

