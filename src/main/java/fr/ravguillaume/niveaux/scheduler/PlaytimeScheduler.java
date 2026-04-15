package fr.ravguillaume.niveaux.scheduler;

import fr.ravguillaume.niveaux.NiveauxPlugin;
import fr.ravguillaume.niveaux.data.PlayerData;
import fr.ravguillaume.niveaux.events.PlayerLevelChangeEvent;
import org.bukkit.Bukkit;
import org.bukkit.entity.Player;
import org.bukkit.scheduler.BukkitRunnable;

import java.util.List;

/**
 * Tâche asynchrone cadencée à 1 minute (1 200 ticks).
 *
 * Responsabilités :
 *  - Incrémenter le temps de jeu des joueurs dans un monde autorisé.
 *  - Déclencher l'auto-save toutes les N minutes (configurable).
 */
public class PlaytimeScheduler extends BukkitRunnable {

    /** 20 ticks/s × 60 s = 1 200 ticks par minute. */
    private static final long TICKS_PER_MINUTE = 20L * 60L;

    private final NiveauxPlugin plugin;
    /** Compteur de minutes écoulées depuis le dernier auto-save. */
    private int minutesSinceLastSave = 0;

    public PlaytimeScheduler(NiveauxPlugin plugin) {
        this.plugin = plugin;
    }

    /**
     * Démarre le scheduler avec un délai initial d'une minute.
     */
    public void start() {
        this.runTaskTimerAsynchronously(plugin, TICKS_PER_MINUTE, TICKS_PER_MINUTE);
    }

    @Override
    public void run() {
        minutesSinceLastSave++;

        List<String> authorizedWorlds = plugin.getConfigManager().getAuthorizedWorlds();

        for (Player player : Bukkit.getOnlinePlayers()) {
            // Vérification du monde
            if (!authorizedWorlds.contains(player.getWorld().getName())) continue;

            PlayerData data = plugin.getPlayerCache().get(player.getUniqueId());
            if (data == null) continue;

            boolean leveledUp = data.addMinute();
            if (leveledUp) {
                final int newLevel = data.getLevel();
                final String name  = data.getName();
                final java.util.UUID uuid = player.getUniqueId();
                Bukkit.getScheduler().runTask(plugin, () ->
                    Bukkit.getPluginManager().callEvent(
                        new PlayerLevelChangeEvent(uuid, name, newLevel - 1, newLevel,
                            PlayerLevelChangeEvent.Reason.PLAYTIME)
                    )
                );
            }
        }

        // Auto-save
        if (minutesSinceLastSave >= plugin.getConfigManager().getAutoSaveInterval()) {
            minutesSinceLastSave = 0;
            int count = plugin.getPlayerCache().size();
            plugin.getDatabaseManager().saveAllPlayers(plugin.getPlayerCache().values());
            plugin.getLogger().info("[Auto-Save] " + count + " joueur(s) sauvegardé(s).");
        }
    }
}
