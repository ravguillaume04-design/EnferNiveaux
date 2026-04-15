package enferplugins.niveaux.scheduler;

import enferplugins.niveaux.NiveauxPlugin;
import enferplugins.niveaux.data.PlayerData;
import enferplugins.niveaux.events.PlayerLevelChangeEvent;
import org.bukkit.Bukkit;
import org.bukkit.entity.Player;
import org.bukkit.scheduler.BukkitRunnable;

import java.util.List;

public class PlaytimeScheduler extends BukkitRunnable {

    private static final long TICKS_PER_MINUTE = 20L * 60L;
    private final NiveauxPlugin plugin;
    private int minutesSinceLastSave = 0;

    public PlaytimeScheduler(NiveauxPlugin plugin) { this.plugin = plugin; }

    public void start() { this.runTaskTimerAsynchronously(plugin, TICKS_PER_MINUTE, TICKS_PER_MINUTE); }

    @Override
    public void run() {
        minutesSinceLastSave++;
        List<String> authorizedWorlds = plugin.getConfigManager().getAuthorizedWorlds();
        for (Player player : Bukkit.getOnlinePlayers()) {
            if (!authorizedWorlds.contains(player.getWorld().getName())) continue;
            PlayerData data = plugin.getPlayerCache().get(player.getUniqueId());
            if (data == null) continue;
            boolean leveledUp = data.addMinute();
            if (leveledUp) {
                final int newLevel = data.getLevel();
                final String name = data.getName();
                final java.util.UUID uuid = player.getUniqueId();
                Bukkit.getScheduler().runTask(plugin, () ->
                    Bukkit.getPluginManager().callEvent(new PlayerLevelChangeEvent(uuid, name, newLevel - 1, newLevel, PlayerLevelChangeEvent.Reason.PLAYTIME)));
            }
        }
        if (minutesSinceLastSave >= plugin.getConfigManager().getAutoSaveInterval()) {
            minutesSinceLastSave = 0;
            int count = plugin.getPlayerCache().size();
            plugin.getDatabaseManager().saveAllPlayers(plugin.getPlayerCache().values());
            plugin.getLogger().info("[Auto-Save] " + count + " joueur(s) sauvegardé(s).");
        }
    }
}
