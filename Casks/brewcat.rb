cask "brewcat" do
  version "0.1.2.7"
  sha256 "335cc31932c8d591faae9f32c85d0ef69c492ad634a794c5b2199895574f1c24"

  url "https://github.com/1985epma/homebrew-brewcat/releases/download/v#{version}/brewcat-#{version}.dmg"
  name "brewcat"
  desc "Visual catalog of Homebrew packages, skills and MCP servers"
  homepage "https://github.com/1985epma/homebrew-brewcat"

  depends_on formula: "python-tk"

  app "brewcat.app"

  # The app is not notarized by Apple; remove the quarantine flag so it opens without a Gatekeeper warning.
  postflight do
    system_command "/usr/bin/xattr",
                   args: ["-dr", "com.apple.quarantine", "#{appdir}/brewcat.app"],
                   sudo: false
  end

  zap trash: [
    "~/Applications/brewcat.app",
    "~/Library/Application Support/brewcat",
  ]
end
