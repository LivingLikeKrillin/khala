public enum GradeType {
    BOSS(3),
    MANAGER(2),
    MEMBER(1);

    private final int level;

    GradeType(int level) {
        this.level = level;
    }
}
