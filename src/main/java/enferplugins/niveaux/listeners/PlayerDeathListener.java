package enferplugins.niveaux.listeners;

import enferplugins.niveaux.NiveauxPlugin;
import enferplugins.niveaux.data.PlayerData;
import enferplugins.niveaux.events.PlayerLevelChangeEvent;
import org.bukkit.Bukkit;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.entity.PlayerDeathEvent;

public class PlayerDeathListener implements Listener {

    private final NiveauxPlugin plugin;
    public PlayerDeathListener(NiveauxPlugin plugin) { this.plugin = plugin; }

    @EventHandler(priority = EventPriority.NORMAL)
    public void onPlayerDeath(PlayerDeathEvent event) {
        PlayerData data = plugin.getPlayerCache().get(event.getEntity().getUniqueId());
        if (data == null) return;
        int oldLevel = data.getLevel();
        data.reset();
        Bukkit.getPluginManager().callEvent(new PlayerLevelChangeEvent(
            event.getEntity().getUniqueId(), event.getEntity().getName(),
            oldLevel, 0, PlayerLevelChangeEvent.Reason.DEATH_RESET));
    }
}
