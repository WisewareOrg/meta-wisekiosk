# Why TST008<!-- Sustained network load --> could not apply its network load on the bench board

| | |
|---|---|
| **Issue** | #408 TST008<!-- Sustained network load --> cannot apply its network load on the bench board |
| **Status** | concluded → code change |
| **Opened / concluded** | 2026-11-25 / 2026-11-26 |


## What happened

From 17:57 on 25 Nov to about 00:10 on 26 Nov, TST008<!-- Sustained network load --> came back invalid on the
bench in every run but two: the load was not applied, at 0.39 to 0.69 MB/s against its 1.0 MB/s floor. It did so on
main's own image as well as on the branch's. On the bench, main (`a47f215`) gave 1 valid call of 3
(`20261126T044038Z`, `20261126T044314Z`, `20261126T044554Z`); the branch gave 0 of 6. Prod passed 3 of 3 on main's
image in the same hour (`20261126T042450Z`, `20261126T042822Z`, `20261126T043154Z`).

**Ruled out by those runs:** the image (main's own image failed on the bench), and a full journal on `/data`. Three
calls with the journal at its cap and three after its archived files were moved aside, with no reboot between, were
all invalid (`20261126T035001Z` to `20261126T040259Z`).

## The cause, as measured

On the same image, the bench's link sat at 802.11b rates and prod's did not:

| | bench, before | prod, before | bench, after | prod, after |
|---|---|---|---|---|
| channel | 10 | 10 | 2 | 2 |
| signal | -57 dBm | -32 dBm | -54 dBm | -38 dBm |
| tx bitrate | **5.5 Mbit/s** (802.11b) | 72.2 Mbit/s (HT) | 72.2 Mbit/s (HT) | 72.2 Mbit/s (HT) |
| failed sends | **26 in 55 s** | 4 in 12 h | 0 in 11 min | 2 in 24 min |

The two boards are identical on the board side: hardware revision, kernel, Wi-Fi firmware and its files, radio
capabilities, regulatory setting, power save, supply voltage and Wi-Fi configuration. The link recovered after two
resets: the AP's reboot, which moved it from channel 10 to channel 2, and the bench's power cut.

**Not separated:** which of the two resets cleared it. Either the channel was the problem, through interference or
congestion that the bench's weaker signal had no margin for, or the bench's radio held a state that only a power
cut clears. No reading of channel 10's occupancy was taken, and when the AP went to channel 10 is not known.

## What changed in the suite

TST008<!-- Sustained network load --> now reads the board's link before it pushes any load. If the link's transmit rate is at or below 11 Mbit/s,
the top rate of 802.11b, the call stops as invalid and names the rate. It no longer pushes a load the link cannot
carry and reports a minute later that the load was not applied. Every TST008<!-- Sustained network load --> call records the link's rate and mode,
so an invalid result shows the link it met.
