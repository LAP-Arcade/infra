terraform {
  required_providers {
    freebox = {
      source = "registry.terraform.io/NikolaLohinski/freebox"
    }
  }

  backend "s3" {
    bucket = "terraform"
    key    = "lap/freebox.tfstate"
    region = "laffey-ii"

    endpoints = {
      s3 = "https://s3.tina.moe"
    }

    use_path_style              = true
    use_lockfile                = true
    skip_credentials_validation = true
    skip_region_validation      = true
  }
}

variable "FREEBOX_TOKEN" {
  sensitive = true
  default   = "http://mafreebox.freebox.fr"
}

variable "FREEBOX_ENDPOINT" {
  sensitive = true
}

provider "freebox" {
  endpoint    = var.FREEBOX_ENDPOINT
  api_version = "v16"
  app_id      = "terraform-provider-freebox"
  token       = var.FREEBOX_TOKEN
}

resource "freebox_vpn_server" "wireguard" {
  vpn_id      = "wireguard"
  enabled     = true
  enable_ipv4 = true
  port        = 9078
}

import {
  to = freebox_vpn_server.wireguard
  id = "wireguard"
}
