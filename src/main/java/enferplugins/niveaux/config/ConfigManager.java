package enferplugins.niveaux.config;

import enferplugins.niveaux.NiveauxPlugin;

import java.util.List;

public class ConfigManager {

    private final NiveauxPlugin plugin;
    public ConfigManager(NiveauxPlugin plugin) { this.plugin = plugin; }
    public void reload() { plugin.reloadConfig(); }
    public String getDatabaseHost() { return plugin.getConfig().getString("database.host", "localhost"); }
    public int getDatabasePort() { return plugin.getConfig().getInt("database.port", 3306); }
    public String getDatabaseName() { return plugin.getConfig().getString("database.name", "minecraft"); }
    public String getDatabaseUser() { return plugin.getConfig().getString("database.username", "root"); }
    public String getDatabasePassword() { return plugin.getConfig().getString("database.password", "password"); }
    public List<String> getAuthorizedWorlds() { return plugin.getConfig().getStringList("mondes-autorises"); }
    public int getAutoSaveInterval() { return Math.max(1, plugin.getConfig().getInt("auto-save-interval", 5)); }
}
