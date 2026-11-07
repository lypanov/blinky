-- 720p60 TMDS for the Primer 20K Dock.
--
-- Raster is CEA-861 1280x720p60 (1650x750, 74.25 MHz, positive sync),
-- the mode the capture card locks from NESTang. The Beeb scandoubler
-- line is 864 clocks at 27 MHz. BSRAM is full, so this is one
-- monochrome line in registers (any non-black nibble), not a frame
-- store. Each HDMI line shows one captured scandoubler line in the
-- left 864 pixels. The rest of the active line is black. The capture
-- is free-running, so the picture is not locked to the 60 Hz frame.
-- Mode 7 text is white, so one bit is the boot screen.
--
-- pll1_lock, reset_n and mon are still ports. They are synchronised
-- and not drawn.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity hdmi_720p is
    port (
        clk_27    : in  std_logic;
        r4        : in  std_logic_vector(3 downto 0);
        g4        : in  std_logic_vector(3 downto 0);
        b4        : in  std_logic_vector(3 downto 0);
        hs        : in  std_logic;
        vs        : in  std_logic;
        pll1_lock : in  std_logic;
        reset_n   : in  std_logic;
        mon       : in  std_logic_vector(5 downto 0);
        clk_pix   : in  std_logic;
        tmds_r    : out std_logic_vector(9 downto 0);
        tmds_g    : out std_logic_vector(9 downto 0);
        tmds_b    : out std_logic_vector(9 downto 0)
    );
end entity;

architecture rtl of hdmi_720p is

    constant H_ACT  : integer := 1280;
    constant H_FP   : integer := 110;
    constant H_SYNC : integer := 40;
    constant H_BP   : integer := 220;
    constant H_TOT  : integer := 1650;
    constant V_ACT  : integer := 720;
    constant V_FP   : integer := 5;
    constant V_SYNC : integer := 5;
    constant V_BP   : integer := 20;
    constant V_TOT  : integer := 750;
    constant LINE   : integer := 864;

    attribute syn_ramstyle : string;

    signal bank0 : std_logic_vector(LINE - 1 downto 0) := (others => '0');
    signal bank1 : std_logic_vector(LINE - 1 downto 0) := (others => '0');
    attribute syn_ramstyle of bank0 : signal is "registers";
    attribute syn_ramstyle of bank1 : signal is "registers";

    signal wr_bank : std_logic := '0';
    signal hs_d    : std_logic := '0';
    signal cap_i   : integer range 0 to LINE - 1 := 0;
    signal seen_27 : std_logic := '0';
    signal hs_slow : std_logic := '0';
    signal line_div : integer range 0 to 8191 := 0;

    signal bank_s1, bank_s2, latched : std_logic := '0';
    signal lock_s1, lock_s2 : std_logic := '0';
    signal rst_s1, rst_s2 : std_logic := '0';
    signal seen_s1, seen_s2 : std_logic := '0';
    signal slow_s1, slow_s2 : std_logic := '0';
    signal mon_s1, mon_s2 : std_logic_vector(5 downto 0) := (others => '0');
    signal aligned : std_logic := '0';
    signal vs_s1, vs_s2 : std_logic := '0';
    signal h : integer range 0 to H_TOT - 1 := 0;
    signal v : integer range 0 to V_TOT - 1 := 0;

    signal pix_r, pix_g, pix_b : std_logic_vector(7 downto 0);
    signal blank, oh, ov : std_logic;

begin

    capture : process (clk_27)
        variable bitv : std_logic;
        variable xi : integer range 0 to LINE - 1;
    begin
        if rising_edge(clk_27) then
            bitv := '0';
            if r4 /= "0000" or g4 /= "0000" or b4 /= "0000" then
                bitv := '1';
                seen_27 <= '1';
            end if;
            -- Free-running line. The scandoubler hsync was not a reliable
            -- frame for the ULA pixels (its line RAM was read as black),
            -- so the sample clock just chops the ULA stream into 864-bit lines.
            xi := cap_i;
            if wr_bank = '0' then
                bank0(xi) <= bitv;
            else
                bank1(xi) <= bitv;
            end if;
            if cap_i = LINE - 1 then
                cap_i <= 0;
                wr_bank <= not wr_bank;
            else
                cap_i <= cap_i + 1;
            end if;
            hs_d <= hs;
            if hs_d = '1' and hs = '0' then
                if line_div = 8191 then
                    line_div <= 0;
                    hs_slow <= not hs_slow;
                else
                    line_div <= line_div + 1;
                end if;
            end if;
        end if;
    end process;

    raster : process (clk_pix)
        variable idx : integer range 0 to LINE - 1;
        variable src : std_logic;
        variable pr, pg, pb : std_logic_vector(7 downto 0);
    begin
        if rising_edge(clk_pix) then
            bank_s1 <= wr_bank;
            bank_s2 <= bank_s1;
            lock_s1 <= pll1_lock;
            lock_s2 <= lock_s1;
            rst_s1 <= reset_n;
            rst_s2 <= rst_s1;
            seen_s1 <= seen_27;
            seen_s2 <= seen_s1;
            slow_s1 <= hs_slow;
            slow_s2 <= slow_s1;
            mon_s1 <= mon;
            mon_s2 <= mon_s1;
            vs_s1 <= vs;
            vs_s2 <= vs_s1;

            if h = H_TOT - 1 then
                h <= 0;
                latched <= bank_s2;
                if aligned = '0' and vs_s2 = '1' and vs_s1 = '0' then
                    v <= 0;
                    aligned <= '1';
                elsif v = V_TOT - 1 then
                    v <= 0;
                else
                    v <= v + 1;
                end if;
            else
                h <= h + 1;
            end if;

            pr := (others => '0');
            pg := (others => '0');
            pb := (others => '0');
            if v < V_ACT and h < LINE then
                idx := h;
                if latched = '0' then
                    src := bank1(idx);
                else
                    src := bank0(idx);
                end if;
                if src = '1' then
                    pr := (others => '1');
                    pg := (others => '1');
                    pb := (others => '1');
                end if;
            end if;

            pix_r <= pr;
            pix_g <= pg;
            pix_b <= pb;

            if h >= H_ACT or v >= V_ACT then
                blank <= '1';
            else
                blank <= '0';
            end if;
            if h >= H_ACT + H_FP and h < H_ACT + H_FP + H_SYNC then
                oh <= '1';
            else
                oh <= '0';
            end if;
            if v >= V_ACT + V_FP and v < V_ACT + V_FP + V_SYNC then
                ov <= '1';
            else
                ov <= '0';
            end if;
        end if;
    end process;

    enc : entity work.hdmi
        generic map (
            FREQ => 74250000,
            FS   => 48000,
            CTS  => 74250,
            N    => 6144
        )
        port map (
            I_CLK_PIXEL    => clk_pix,
            I_R            => pix_r,
            I_G            => pix_g,
            I_B            => pix_b,
            I_BLANK        => blank,
            I_HSYNC        => oh,
            I_VSYNC        => ov,
            I_ASPECT_169   => '1',
            I_AUDIO_ENABLE => '0',
            I_AUDIO_PCM_L  => (others => '0'),
            I_AUDIO_PCM_R  => (others => '0'),
            O_RED          => tmds_r,
            O_GREEN        => tmds_g,
            O_BLUE         => tmds_b
        );

end architecture;
