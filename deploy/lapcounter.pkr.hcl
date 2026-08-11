packer {
  required_plugins {
    arm = {
      version = ">= 1.0.0"
      source  = "github.com/mkaczanowski/arm"
    }
  }
}

# Raspberry Pi OS Lite, 32-bit (armhf), trixie.
#
# 32-bit deliberately, to match the deployed Pi. Note the trade-off recorded in
# deploy/ram-analysis.md: armhf has no prebuilt psycopg2-binary wheel, so
# dbwriter compiles from source. That cost is paid once in CI, not here - this
# image only *loads* prebuilt container images.
#
# Pinned for reproducibility. The moving alternative is
# https://downloads.raspberrypi.com/raspios_lite_armhf_latest (+ .sha256),
# which currently redirects to exactly this file.
locals {
  base_url     = "https://downloads.raspberrypi.com/raspios_lite_armhf/images/raspios_lite_armhf-2026-06-19/2026-06-18-raspios-trixie-armhf-lite.img.xz"
  checksum_url = "https://downloads.raspberrypi.com/raspios_lite_armhf/images/raspios_lite_armhf-2026-06-19/2026-06-18-raspios-trixie-armhf-lite.img.xz.sha256"
}

source "arm" "raspios" {
  file_urls             = [local.base_url]
  file_checksum_url     = local.checksum_url
  file_checksum_type    = "sha256"
  file_target_extension = "xz"
  file_unarchive_cmd    = ["xz", "--decompress", "$FILEPATH"]

  image_build_method = "resize"
  image_path         = "output/lapcounter.img"

  # Must hold the OS (~2.5GB) plus the saved container images (~2GB) plus room
  # for docker load to unpack them. PiShrink cuts the artifact back down
  # afterwards, and the rootfs auto-expands on first boot.
  image_size = "9G"
  image_type = "dos"

  image_partitions {
    name         = "boot"
    type         = "c"
    start_sector = "8192"
    filesystem   = "fat"
    size         = "512M"
    mountpoint   = "/boot/firmware"
  }
  image_partitions {
    name         = "root"
    type         = "83"
    start_sector = "1056768"
    filesystem   = "ext4"
    size         = "0"
    mountpoint   = "/"
  }

  image_chroot_env = ["PATH=/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin"]

  # armhf userland -> arm (32-bit) qemu, not aarch64.
  qemu_binary_source_path      = "/usr/bin/qemu-arm-static"
  qemu_binary_destination_path = "/usr/bin/qemu-arm-static"
}

build {
  sources = ["source.arm.raspios"]

  provisioner "shell" {
    inline = ["mkdir -p /opt/lapcounter /var/lib/lapcounter"]
  }

  # The race-meet compose file, NOT compose.pi.yaml - that one targets
  # lapcounter.local and omits dbwriter entirely (so no lap persistence).
  provisioner "file" {
    source      = "compose.race.yaml"
    destination = "/opt/lapcounter/compose.yaml"
  }

  provisioner "file" {
    sources     = ["../mosquitto", "../database"]
    destination = "/opt/lapcounter/"
  }

  # Prebuilt container images, so first boot needs no internet.
  # Produced by the workflow: docker pull --platform linux/arm/v7 | docker save | zstd
  provisioner "file" {
    source      = "output/images.tar.zst"
    destination = "/opt/lapcounter/images.tar.zst"
  }

  provisioner "file" {
    sources = [
      "image/firstboot.sh",
      "image/lapcounter-firstboot.service",
      "lapcounter.service",
    ]
    destination = "/tmp/"
  }

  # Editable from Windows/macOS on the FAT partition, applied on first boot.
  provisioner "file" {
    source      = "image/lapcounter.conf.example"
    destination = "/boot/firmware/lapcounter.conf"
  }

  provisioner "shell" {
    script = "image/setup-image.sh"
  }
}
