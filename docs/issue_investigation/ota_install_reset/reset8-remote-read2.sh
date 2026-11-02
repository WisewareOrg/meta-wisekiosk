# read-only: which driver binds each mmc host
for h in /sys/class/mmc_host/mmc*; do
  echo "$h $(readlink -f $h/device) driver=$(basename $(readlink -f $h/device/driver))"
done
