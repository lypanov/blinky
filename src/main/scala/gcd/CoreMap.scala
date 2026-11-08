package gcd

import java.io.File

// sim/link_inner.py writes this next to the ROM image. The numbers are
// elaboration constants: the fetch translation, the init-stream window,
// the placed-body window, and the sector-pair table.
case class CoreMap(
    stubWords: Int,
    coreBase: Int,
    coreWords: Int,
    coreRom: Int,
    initBase: Int,
    initWords: Int,
    initRom: Int,
    bodyLo: Int,
    bodyHi: Int,
    body: Int,
    light: Int,
    sectorRom: Int,
    sectorWords: Int,
    sectorPairs: Int,
    romWords: Int,
    delayWord: Long,
    desc: Int,
    stringAt: Int
) {
  def coreEnd: Int = coreBase + coreWords * 4
  def initEnd: Int = initBase + initWords * 4
  def stubEnd: Int = 0x80 + stubWords * 4
}

object CoreMap {
  def load(projectRoot: String): Option[CoreMap] = {
    val file = new File(projectRoot, "sim/visualizer/imem/core.map")
    if (!file.isFile) return None
    val kv = scala.io.Source.fromFile(file).getLines().flatMap { line =>
      val text = line.trim
      if (text.isEmpty || !text.contains("=")) None
      else {
        val cut = text.indexOf('=')
        val key = text.substring(0, cut)
        val raw = text.substring(cut + 1)
        val value = if (raw.startsWith("0x") || raw.startsWith("0X")) java.lang.Long.parseLong(raw.substring(2), 16)
        else raw.toLong
        Some(key -> value)
      }
    }.toMap
    if (kv.getOrElse("split", 0L) != 1L) return None
    def n(key: String): Int = {
      val v = kv.getOrElse(key, throw new RuntimeException(s"core.map missing $key"))
      if (v < 0 || v > Int.MaxValue) throw new RuntimeException(s"core.map $key=$v")
      v.toInt
    }
    Some(CoreMap(
      stubWords = n("stub_words"),
      coreBase = n("core_base"),
      coreWords = n("core_words"),
      coreRom = n("core_rom"),
      initBase = n("init_base"),
      initWords = n("init_words"),
      initRom = n("init_rom"),
      bodyLo = n("body_lo"),
      bodyHi = n("body_hi"),
      body = n("body"),
      light = n("light"),
      sectorRom = n("sector_rom"),
      sectorWords = n("sector_words"),
      sectorPairs = n("sector_pairs"),
      romWords = n("rom_words"),
      delayWord = kv.getOrElse("delay_word", 0L),
      desc = n("desc"),
      stringAt = n("string")
    ))
  }
}
