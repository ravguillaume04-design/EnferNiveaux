package enferplugins.niveaux.listeners;

import enferplugins.niveaux.NiveauxPlugin;
import enferplugins.niveaux.data.PlayerData;
import org.bukkit.Bukkit;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerQuitEvent;

import java.util.UUID;

public class PlayerConnectionListener implements Listener {

    private final NiveauxPlugin plugin;
    public PlayerConnectionListener(NiveauxPlugin plugin) { this.plugin = plugin; }

    @EventHandler(priority = EventPriority.NORMAL)
    public void onPlayerJoin(PlayerJoinEvent event) {
        final UUID uuid = event.getPlayer().getUniqueId();
        final String name = event.getPlayer().getName();
        Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
            PlayerData data = plugin.getDatabaseManager().loadPlayer(uuid, name);
            data.setName(name);
            plugin.getPlayerCache().put(uuid, data);
        });
    }

    @EventHandler(priority = EventPriority.NORMAL)
    public void onPlayerQuit(PlayerQuitEvent event) {
        final UUID uuid = event.getPlayer().getUniqueId();
        final PlayerData data = plugin.getPlayerCache().remove(uuid);
        if (data != null) Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> plugin.getDatabaseManager().savePlayer(data));
    }
}
