class Brewcat < Formula
  desc "Visual catalog of Homebrew packages, skills and MCP servers for devs and gamers"
  homepage "https://github.com/1985epma/homebrew-utils"
  url "https://github.com/1985epma/homebrew-utils/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "PLACEHOLDER"

  depends_on "python-tk"

  def install
    libexec.install "app.py", "catalog_data.py", "extras_tab.py"
    (bin/"brewcat").write <<~SH
      #!/bin/bash
      exec "#{HOMEBREW_PREFIX}/bin/python3" "#{libexec}/app.py" "$@"
    SH
  end

  def caveats
    <<~EOS
      Run the app with:
        brewcat
    EOS
  end

  test do
    ENV.prepend_path "PYTHONPATH", libexec
    system "#{HOMEBREW_PREFIX}/bin/python3", "-c", "import catalog_data; assert len(catalog_data.ITEMS) > 100"
  end
end
