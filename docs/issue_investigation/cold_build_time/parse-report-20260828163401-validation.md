# Buildstats report: build/tmp-raspberrypi0-wifi/buildstats/20260828163401

Real (non-setscene) task files parsed: 2696
Setscene task files (excluded): 321
Unparsed/skipped files: 0
Wall time (first task Started -> last task Ended): 6h50m53s (24653.0s)
Cold full build (first task Started -> do_image_complete Ended): 6h50m52s (24652.1s)
WebKit rebuild (webkitgtk3 do_configure Started -> do_image_complete Ended): 5h01m37s (18097.5s)

build_stats (run-root summary file):
```
Host Info: Linux ca239972637b 6.18.33.2-microsoft-standard-WSL2 #1 SMP PREEMPT_DYNAMIC Thu Jun 18 21:54:43 UTC 2026 x86_64 
Build Started: 1787934846.50 
Uncompressed Rootfs size: 253M	/work/build/tmp-raspberrypi0-wifi/work/raspberrypi0_wifi-poky-linux-gnueabi/core-image-base/1.0/rootfs
Elapsed time: 24668.84 seconds 
CPU usage: 39.6%
```

## Top 25 recipes by summed real-task elapsed time

| # | recipe | summed elapsed | real tasks | share of wall |
|---|---|---|---|---|
| 1 | webkitgtk3-2.44.3-r0 | 4h58m49s (17929s) | 13 | 72.7% |
| 2 | linux-raspberrypi-1_6.12.93+git-r0 | 2h04m59s (7499s) | 31 | 30.4% |
| 3 | systemd-1_255.21-r0 | 0h24m10s (1450s) | 13 | 5.9% |
| 4 | python3-3.12.13-r0 | 0h20m24s (1224s) | 13 | 5.0% |
| 5 | perl-5.38.4-r0 | 0h19m35s (1175s) | 10 | 4.8% |
| 6 | glibc-locale-2.39+git-r0 | 0h19m19s (1159s) | 8 | 4.7% |
| 7 | icu-74-2-r0 | 0h17m26s (1046s) | 12 | 4.2% |
| 8 | mesa-gl-2_24.0.7-r0 | 0h16m34s (994s) | 13 | 4.0% |
| 9 | harfbuzz-8.3.0-r0 | 0h15m48s (948s) | 13 | 3.8% |
| 10 | glibc-2.39+git-r1 | 0h14m57s (897s) | 15 | 3.6% |
| 11 | libunistring-1.2-r0 | 0h14m54s (894s) | 11 | 3.6% |
| 12 | gtk+3-3.24.41-r0 | 0h13m36s (816s) | 13 | 3.3% |
| 13 | openssl-3.5.7-r0 | 0h13m21s (801s) | 11 | 3.2% |
| 14 | glib-2.0-1_2.78.6-r0 | 0h11m01s (661s) | 13 | 2.7% |
| 15 | gstreamer1.0-plugins-base-1.22.12-r0 | 0h09m58s (598s) | 13 | 2.4% |
| 16 | util-linux-2.39.3-r0 | 0h09m58s (598s) | 11 | 2.4% |
| 17 | gnutls-3.8.4-r0 | 0h09m44s (584s) | 13 | 2.4% |
| 18 | imagemagick-7.1.1-47-r0 | 0h09m12s (552s) | 12 | 2.2% |
| 19 | ncurses-6.4-r0 | 0h09m10s (550s) | 11 | 2.2% |
| 20 | vala-0.56.15-r0 | 0h08m43s (523s) | 13 | 2.1% |
| 21 | gcc-runtime-13.4.0-r0 | 0h08m17s (497s) | 11 | 2.0% |
| 22 | fftw-3.3.10-r0 | 0h07m36s (456s) | 11 | 1.9% |
| 23 | coreutils-9.4-r0 | 0h07m35s (455s) | 10 | 1.8% |
| 24 | sqlite3-3_3.45.3-r0 | 0h06m43s (403s) | 11 | 1.6% |
| 25 | libx11-1_1.8.9-r0 | 0h06m20s (380s) | 11 | 1.5% |

## Top 25 individual tasks by elapsed time

| # | recipe:task | elapsed | ru_maxrss (KB) | child_maxrss (KB) | started (rel to run start) |
|---|---|---|---|---|---|
| 1 | webkitgtk3-2.44.3-r0:do_compile | 4h51m59s (17519s) | 194356 | 4060376 | 1h51m28s |
| 2 | linux-raspberrypi-1_6.12.93+git-r0:do_compile_kernelmodules | 1h08m34s (4114s) | 81252 | 329076 | 0h22m54s |
| 3 | linux-raspberrypi-1_6.12.93+git-r0:do_compile | 0h19m14s (1154s) | 71180 | 243700 | 0h03m38s |
| 4 | systemd-1_255.21-r0:do_compile | 0h16m21s (981s) | 84636 | 230036 | 1h07m27s |
| 5 | glibc-locale-2.39+git-r0:do_package | 0h15m19s (919s) | 119780 | 189960 | 2h02m35s |
| 6 | mesa-gl-2_24.0.7-r0:do_compile | 0h14m24s (864s) | 84188 | 393952 | 1h06m42s |
| 7 | linux-raspberrypi-1_6.12.93+git-r0:do_create_spdx | 0h13m24s (804s) | 285704 | 285704 | 2h24m44s |
| 8 | harfbuzz-8.3.0-r0:do_compile | 0h13m06s (786s) | 84108 | 1215004 | 1h13m27s |
| 9 | icu-74-2-r0:do_compile | 0h12m38s (758s) | 82588 | 197076 | 0h58m55s |
| 10 | glibc-2.39+git-r1:do_compile | 0h10m29s (629s) | 112232 | 162288 | 0h00m19s |
| 11 | openssl-3.5.7-r0:do_compile | 0h10m20s (620s) | 81636 | 133848 | 0h30m53s |
| 12 | linux-raspberrypi-1_6.12.93+git-r0:do_package_write_ipk | 0h08m00s (480s) | 123796 | 123796 | 2h26m47s |
| 13 | gtk+3-3.24.41-r0:do_compile | 0h07m48s (468s) | 85992 | 333096 | 1h32m23s |
| 14 | linux-raspberrypi-1_6.12.93+git-r0:do_package | 0h07m38s (458s) | 148500 | 144808 | 1h56m22s |
| 15 | libunistring-1.2-r0:do_compile | 0h07m34s (454s) | 83060 | 79368 | 1h20m02s |
| 16 | perl-5.38.4-r0:do_compile | 0h06m38s (398s) | 85728 | 303568 | 2h14m50s |
| 17 | libunistring-1.2-r0:do_configure | 0h06m32s (392s) | 84092 | 84092 | 1h13m28s |
| 18 | gstreamer1.0-plugins-base-1.22.12-r0:do_compile | 0h06m03s (363s) | 85316 | 261088 | 1h40m52s |
| 19 | glib-2.0-1_2.78.6-r0:do_compile | 0h06m02s (362s) | 82800 | 210892 | 0h42m54s |
| 20 | vala-0.56.15-r0:do_compile | 0h05m32s (332s) | 83732 | 255704 | 1h19m11s |
| 21 | sqlite3-3_3.45.3-r0:do_compile | 0h05m30s (330s) | 81508 | 509496 | 0h37m09s |
| 22 | perl-5.38.4-r0:do_configure | 0h05m29s (329s) | 85672 | 81916 | 2h09m20s |
| 23 | python3-3.12.13-r0:do_compile | 0h05m26s (326s) | 84252 | 279716 | 0h48m08s |
| 24 | imagemagick-7.1.1-47-r0:do_compile | 0h05m16s (316s) | 85804 | 563932 | 2h17m43s |
| 25 | python3-3.12.13-r0:do_configure | 0h05m11s (311s) | 83836 | 83836 | 0h42m53s |

## Concurrency per 10-minute bucket

| bucket (offset from run start) | distinct tasks touching window | point-sample concurrency (threads busy) | sample tasks touching window |
|---|---|---|---|
| 0h00m00s-0h10m00s | 500 | 1 | acl-2.3.2-r0:do_cve_check, acl-native-2.3.2-r0:do_cve_check, adwaita-icon-theme-45.0-r0:do_cve_check, alsa-lib-1.2.11-r0:do_cve_check |
| 0h10m00s-0h20m00s | 24 | 2 | gcc-runtime-13.4.0-r0:do_collect_spdx_deps, gcc-runtime-13.4.0-r0:do_configure, gcc-runtime-13.4.0-r0:do_prepare_recipe_sysroot, glibc-2.39+git-r1:do_compile |
| 0h20m00s-0h30m00s | 115 | 2 | bash-completion-2.12.0-r0:do_compile, bash-completion-2.12.0-r0:do_configure, bash-completion-2.12.0-r0:do_install, bash-completion-2.12.0-r0:do_populate_sysroot |
| 0h30m00s-0h40m00s | 66 | 6 | bash-completion-2.12.0-r0:do_package, bzip2-1.0.8-r0:do_populate_sysroot, gdbm-1.23-r0:do_compile, gdbm-1.23-r0:do_configure |
| 0h40m00s-0h50m00s | 108 | 6 | acl-2.3.2-r0:do_configure, acl-2.3.2-r0:do_prepare_recipe_sysroot, attr-2.5.1-r0:do_compile, attr-2.5.1-r0:do_configure |
| 0h50m00s-1h00m00s | 125 | 6 | acl-2.3.2-r0:do_compile, acl-2.3.2-r0:do_configure, acl-2.3.2-r0:do_install, acl-2.3.2-r0:do_package |
| 1h00m00s-1h10m00s | 96 | 6 | cairo-1.18.0-r0:do_package, cairo-1.18.0-r0:do_packagedata, expat-2.6.4-r0:do_collect_spdx_deps, expat-2.6.4-r0:do_create_spdx |
| 1h10m00s-1h20m00s | 45 | 5 | font-util-1.4.1-r0:do_compile, font-util-1.4.1-r0:do_install, gdbm-1.23-r0:do_collect_spdx_deps, gdbm-1.23-r0:do_create_spdx |
| 1h20m00s-1h30m00s | 76 | 6 | at-spi2-core-2.50.1-r0:do_compile, at-spi2-core-2.50.1-r0:do_configure, at-spi2-core-2.50.1-r0:do_prepare_recipe_sysroot, attr-2.5.1-r0:do_collect_spdx_deps |
| 1h30m00s-1h40m00s | 167 | 6 | acl-2.3.2-r0:do_collect_spdx_deps, acl-2.3.2-r0:do_create_spdx, alsa-lib-1.2.11-r0:do_compile, alsa-lib-1.2.11-r0:do_configure |
| 1h40m00s-1h50m00s | 165 | 6 | alsa-lib-1.2.11-r0:do_package, avahi-0.8-r0:do_configure, avahi-0.8-r0:do_prepare_recipe_sysroot, bash-5.2.21-r0:do_configure |
| 1h50m00s-2h00m00s | 170 | 5 | at-spi2-core-2.50.1-r0:do_collect_spdx_deps, at-spi2-core-2.50.1-r0:do_create_spdx, avahi-0.8-r0:do_compile, avahi-0.8-r0:do_configure |
| 2h00m00s-2h10m00s | 119 | 6 | adwaita-icon-theme-45.0-r0:do_prepare_recipe_sysroot, avahi-0.8-r0:do_populate_sysroot, busybox-1.36.1-r0:do_compile, busybox-1.36.1-r0:do_install |
| 2h10m00s-2h20m00s | 163 | 6 | adwaita-icon-theme-45.0-r0:do_compile, adwaita-icon-theme-45.0-r0:do_configure, adwaita-icon-theme-45.0-r0:do_install, adwaita-icon-theme-45.0-r0:do_package |
| 2h20m00s-2h30m00s | 408 | 6 | adwaita-icon-theme-45.0-r0:do_collect_spdx_deps, adwaita-icon-theme-45.0-r0:do_create_spdx, adwaita-icon-theme-45.0-r0:do_packagedata, alsa-lib-1.2.11-r0:do_collect_spdx_deps |
| 2h30m00s-2h40m00s | 394 | 5 | acl-2.3.2-r0:do_create_runtime_spdx, acl-2.3.2-r0:do_package_qa, adwaita-icon-theme-45.0-r0:do_create_runtime_spdx, adwaita-icon-theme-45.0-r0:do_package_qa |
| 2h40m00s-2h50m00s | 6 | 6 | glibc-locale-2.39+git-r0:do_create_runtime_spdx, glibc-locale-2.39+git-r0:do_package_qa, linux-raspberrypi-1_6.12.93+git-r0:do_create_runtime_spdx, linux-raspberrypi-1_6.12.93+git-r0:do_deploy |
| 2h50m00s-3h00m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 3h00m00s-3h10m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 3h10m00s-3h20m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 3h20m00s-3h30m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 3h30m00s-3h40m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 3h40m00s-3h50m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 3h50m00s-4h00m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
| 4h00m00s-4h10m00s | 1 | 1 | webkitgtk3-2.44.3-r0:do_compile |
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
| 6h40m00s-6h50m00s | 27 | 1 | core-image-base-1.0-r0:do_create_runtime_spdx, core-image-base-1.0-r0:do_flush_pseudodb, core-image-base-1.0-r0:do_image, core-image-base-1.0-r0:do_image_qa |
| 6h50m00s-7h00m00s | 9 | 1 | core-image-base-1.0-r0:do_image, core-image-base-1.0-r0:do_image_complete, core-image-base-1.0-r0:do_image_ext3, core-image-base-1.0-r0:do_image_ext4 |

## Latest-finishing tasks (top 20 by Ended time) -- tail of the critical path

| # | recipe:task | ended (rel to run start) | started (rel) | elapsed | concurrently running at its start |
|---|---|---|---|---|---|
| 1 | core-image-base-1.0-r0:do_populate_lic_deploy | 6h50m53s | 6h50m53s | 0h00m00s | 0:  |
| 2 | core-image-base-1.0-r0:do_image_complete | 6h50m52s | 6h50m49s | 0h00m03s | 0:  |
| 3 | core-image-base-1.0-r0:do_image_wic | 6h50m48s | 6h50m05s | 0h00m42s | 1: core-image-base-1.0-r0:do_image_ext4 |
| 4 | core-image-base-1.0-r0:do_image_ext3 | 6h50m25s | 6h50m06s | 0h00m19s | 2: core-image-base-1.0-r0:do_image_ext4, core-image-base-1.0-r0:do_image_wic |
| 5 | core-image-base-1.0-r0:do_image_ext4 | 6h50m24s | 6h50m05s | 0h00m19s | 0:  |
| 6 | core-image-base-1.0-r0:do_image_tar | 6h50m21s | 6h50m07s | 0h00m14s | 3: core-image-base-1.0-r0:do_image_ext3, core-image-base-1.0-r0:do_image_ext4, core-image-base-1.0-r0:do_image_wic |
| 7 | core-image-base-1.0-r0:do_rootfs_wicenv | 6h50m04s | 6h50m04s | 0h00m00s | 0:  |
| 8 | core-image-base-1.0-r0:do_write_wks_template | 6h50m03s | 6h50m03s | 0h00m00s | 0:  |
| 9 | core-image-base-1.0-r0:do_image | 6h50m02s | 6h49m57s | 0h00m06s | 0:  |
| 10 | core-image-base-1.0-r0:do_image_qa | 6h49m56s | 6h49m56s | 0h00m00s | 0:  |
| 11 | core-image-base-1.0-r0:do_flush_pseudodb | 6h49m55s | 6h49m55s | 0h00m00s | 0:  |
| 12 | core-image-base-1.0-r0:do_rootfs | 6h49m52s | 6h46m59s | 0h02m54s | 0:  |
| 13 | webkitgtk3-2.44.3-r0:do_package_qa | 6h46m58s | 6h46m02s | 0h00m56s | 3: surf-2.1-r0:do_package, webkitgtk3-2.44.3-r0:do_create_spdx, webkitgtk3-2.44.3-r0:do_package_write_ipk |
| 14 | core-image-base-1.0-r0:do_create_runtime_spdx | 6h46m33s | 6h46m31s | 0h00m02s | 3: kiosk-session-1.0-r0:do_create_runtime_spdx, surf-2.1-r0:do_create_runtime_spdx, webkitgtk3-2.44.3-r0:do_package_qa |
| 15 | surf-2.1-r0:do_create_runtime_spdx | 6h46m31s | 6h46m30s | 0h00m00s | 2: kiosk-session-1.0-r0:do_create_runtime_spdx, webkitgtk3-2.44.3-r0:do_package_qa |
| 16 | kiosk-session-1.0-r0:do_create_runtime_spdx | 6h46m31s | 6h46m30s | 0h00m00s | 1: webkitgtk3-2.44.3-r0:do_package_qa |
| 17 | webkitgtk3-2.44.3-r0:do_create_runtime_spdx | 6h46m30s | 6h46m29s | 0h00m01s | 2: surf-2.1-r0:do_collect_spdx_deps, webkitgtk3-2.44.3-r0:do_package_qa |
| 18 | surf-2.1-r0:do_create_spdx | 6h46m30s | 6h46m30s | 0h00m00s | 2: webkitgtk3-2.44.3-r0:do_create_runtime_spdx, webkitgtk3-2.44.3-r0:do_package_qa |
| 19 | surf-2.1-r0:do_collect_spdx_deps | 6h46m29s | 6h46m29s | 0h00m01s | 1: webkitgtk3-2.44.3-r0:do_package_qa |
| 20 | webkitgtk3-2.44.3-r0:do_create_spdx | 6h46m28s | 6h46m02s | 0h00m27s | 1: surf-2.1-r0:do_package |

Max point-sample concurrency (threads busy) in this run: 6
Mean point-sample concurrency (over non-idle buckets): 2.6
Buckets with exactly 1 task in flight (single-threaded tail): 26 of 43 (260 min)
Buckets with 0 tasks in flight (dead time / bitbake overhead only): 1

