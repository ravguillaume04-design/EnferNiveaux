package enferplugins.niveaux.data;

import java.util.UUID;

public class PlayerData {

    private final UUID uuid;
    private String name;
    private int level;
    private int minutes;

    public PlayerData(UUID uuid, String name, int level, int minutes) {
        this.uuid = uuid; this.name = name; this.level = level; this.minutes = minutes;
    }

    public boolean addMinute() {
        this.minutes++;
        int newLevel = this.minutes / 60;
        if (newLevel > this.level) { this.level = newLevel; return true; }
        return false;
    }

    public void reset() { this.level = 0; this.minutes = 0; }

    public void addLevel(int amount) {
        this.level = Math.max(0, this.level + amount);
        this.minutes = this.level * 60;
    }

    public void removeLevel(int amount) {
        this.level = Math.max(0, this.level - amount);
        this.minutes = this.level * 60;
    }

    public void setLevel(int level) {
        this.level = Math.max(0, level);
        this.minutes = this.level * 60;
    }

    public UUID getUuid() { return uuid; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public int getLevel() { return level; }
    public int getMinutes() { return minutes; }
}
