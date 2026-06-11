packer {
  required_plugins {
    arm = {
      version = ">= 1.0.0"
      source  = "github.com/mkaczanowski/arm"
    }
  }
}

# Update this URL+checksum when a new Raspberry Pi OS release is available.
# Find releases at: https://www.raspberrypi.com/software/operating-systems/
locals {
  base_url      = "https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-2024-11-19/2024-11-19-raspios-bookworm-arm64-lite.img.xz"
  checksum_url  = "https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-2024-11-19/2024-11-19-raspios-bookworm-arm64-lite.img.xz.sha256"
}

source "arm" "raspios" {
  file_urls             = [local.base_url]
  file_checksum_url     = local.checksum_url
  file_checksum_type    = "sha256"
  file_target_extension = "xz"
  file_unarchive_cmd    = ["xz", "--decompress", "$FILEPATH"]

  image_build_method = "resize"
  image_path         = "output/lapcounter.img"
  image_size         = "4G"
  image_type         = "dos"

  image_partitions {
    name         = "boot"
    type         = "c"
    start_sector = "8192"
    filesystem   = "fat"
    size         = "256M"
    mountpoint   = "/boot/firmware"
  }
  image_partitions {
    name         = "root"
    type         = "83"
    start_sector = "532480"
    filesystem   = "ext4"
    size         = "0"
    mountpoint   = "/"
  }

  image_chroot_env = ["PATH=/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin"]

  qemu_binary_source_path      = "/usr/bin/qemu-aarch64-static"
  qemu_binary_destination_path = "/usr/bin/qemu-aarch64-static"
}

build {
  sources = ["source.arm.raspios"]

  provisioner "shell" {
    inline = ["mkdir -p /opt/lapcounter"]
  }

  provisioner "file" {
    source      = "compose.pi.yaml"
    destination = "/opt/lapcounter/compose.yaml"
  }

  provisioner "file" {
    sources     = ["../mosquitto"]
    destination = "/opt/lapcounter/"
  }

  provisioner "file" {
    source      = "lapcounter.service"
    destination = "/etc/systemd/system/lapcounter.service"
  }

  provisioner "shell" {
    script = "setup.sh"
  }
}
