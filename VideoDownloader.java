import java.io.*;
import java.net.*;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.List;
import java.util.zip.*;
import java.util.concurrent.*;
import org.json.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.StandardOpenOption;

/*
 * NanCunChild Programmed Java Version Based On lsy Python Version
 * XDUVideoDownloader
 */

public class VideoDownloader {

    public static void main(String[] args) {
        Arguments arguments = parseArguments(args);
        if (arguments == null) {
            return;
        }
        mainLogic(arguments.liveId, arguments.command, arguments.single);
    }

    private static void mainLogic(String liveidFromCli, String command, boolean single) {
        Scanner scanner = new Scanner(System.in);
        String inputLiveId = liveidFromCli;

        while (true) {
            if (inputLiveId == null || inputLiveId.isEmpty()) {
                System.out.print("请输入 liveId：");
                inputLiveId = scanner.nextLine();
            }

            if (inputLiveId.matches("\\d{1,10}")) {
                break;
            } else {
                System.out.println("liveId 错误，请重新输入：");
                inputLiveId = null;
            }
        }

        JSONArray data = getInitialData(inputLiveId);

        if (data == null || data.length() == 0) {
            System.out.println("没有找到数据，请检查 liveId 是否正确。");
            return;
        }

        JSONObject firstEntry = data.getJSONObject(0);
        long startTime = firstEntry.getJSONObject("startTime").getLong("time");
        String courseCode = getStringFromJson(firstEntry, "courseCode");
        String courseName = getStringFromJson(firstEntry, "courseName");

        // System.out.println(courseCode);
        // System.out.println(courseName);

        Instant startTimeInstant = Instant.ofEpochMilli(startTime);
        ZonedDateTime startTimeZoned = ZonedDateTime.ofInstant(startTimeInstant, ZoneId.of("UTC"));
        int year = startTimeZoned.getYear();

        String saveDir = year + "年" + courseCode + courseName;
        createDirectory(saveDir);

        String csvFilename = saveDir + ".csv";

        List<String[]> rows = new ArrayList<>();
        System.out.println("获取视频链接...");
        for (int i = 0; i < data.length(); i++) {
            JSONObject entry = data.getJSONObject(i);
            // System.out.println(getStringFromJson(entry, "id"));
            String liveId = getStringFromJson(entry, "id");
            if (single && !liveId.equals(inputLiveId)) {
                continue;
            }

            int days = entry.getInt("days");
            int day = entry.getJSONObject("startTime").getInt("day");
            int jie = entry.getInt("jie");

            long entryStartTime = entry.getJSONObject("startTime").getLong("time");
            ZonedDateTime entryTime = ZonedDateTime.ofInstant(Instant.ofEpochMilli(entryStartTime), ZoneId.of("UTC"));
            int month = entryTime.getMonthValue();
            int date = entryTime.getDayOfMonth();

            String[] m3u8Links = getM3u8Links(liveId);
            String pptVideo = m3u8Links[0];
            String teacherTrack = m3u8Links[1];

            rows.add(new String[]{String.valueOf(month), String.valueOf(date), String.valueOf(day), String.valueOf(jie), String.valueOf(days), pptVideo, teacherTrack});
        }

        writeCsv(csvFilename, rows);
        System.out.println(csvFilename + " 文件已创建并写入数据。");

        System.out.println("Downloading videos...");
        for (String[] row : rows) {
            int month = Integer.parseInt(row[0]);
            int date = Integer.parseInt(row[1]);
            int day = Integer.parseInt(row[2]);
            int jie = Integer.parseInt(row[3]);
            int days = Integer.parseInt(row[4]);
            String pptVideo = row[5];
            String teacherTrack = row[6];
            String dayChinese = dayToChinese(day);

            if (pptVideo != null && !pptVideo.isEmpty()) {
                String filename = courseCode + courseName + year + "年" + month + "月" + date + "日第" + days + "周星期" + dayChinese + "第" + jie + "节-pptVideo";
                String filepath = Paths.get(saveDir, filename + ".ts").toString();
                if (Files.exists(Paths.get(filepath))) {
                    System.out.println(filepath + " 已存在，跳过下载。");
                } else {
                    downloadM3u8(pptVideo, filename, saveDir, command);
                }
            }

            if (teacherTrack != null && !teacherTrack.isEmpty()) {
                String filename = courseCode + courseName + year + "年" + month + "月" + date + "日第" + days + "周星期" + dayChinese + "第" + jie + "节-teacherTrack";
                String filepath = Paths.get(saveDir, filename + ".ts").toString();
                if (Files.exists(Paths.get(filepath))) {
                    System.out.println(filepath + " 已存在，跳过下载。");
                } else {
                    downloadM3u8(teacherTrack, filename, saveDir, command);
                }
            }
        }

        System.out.println("所有视频下载完成。");
    }

    private static String getStringFromJson(JSONObject json, String key) {
        Object value = json.get(key);
        if (value instanceof Integer) {
            return Integer.toString((Integer) value);
        } else if (value instanceof String) {
            return (String) value;
        } else {
            throw new JSONException("Unexpected type for key \"" + key + "\": " + value.getClass().getName());
        }
    }

    private static JSONArray getInitialData(String inputLiveId) {
        String url = "http://newesxidian.chaoxing.com/live/listSignleCourse";
        String response = postRequest(url, "liveId=" + inputLiveId);
        if (response == null) {
            return null;
        }
        return new JSONArray(response);
    }

    private static String[] getM3u8Links(String liveId) {
        String url = "http://newesxidian.chaoxing.com/live/getViewUrlHls?liveId=" + liveId + "&status=2";
        String response = getRequest(url);
        if (response == null) {
            return new String[]{"", ""};
        }

        int urlStart = response.indexOf("info=");
        if (urlStart == -1) {
            throw new IllegalArgumentException("info parameter not found in the response");
        }

        String encodedInfo = response.substring(urlStart + 5);
        String decodedInfo = URLDecoder.decode(encodedInfo, StandardCharsets.UTF_8);
        JSONObject infoJson = new JSONObject(decodedInfo);

        JSONObject videoPaths = infoJson.optJSONObject("videoPath");
        String pptVideo = videoPaths != null ? videoPaths.optString("pptVideo", "") : "";
        String teacherTrack = videoPaths != null ? videoPaths.optString("teacherTrack", "") : "";

        return new String[]{pptVideo, teacherTrack};
    }

    private static void downloadM3u8(String url, String filename, String saveDir, String command) {
        if (command.isEmpty()) {
            String os = System.getProperty("os.name").toLowerCase();
            if (os.contains("win")) {
                command = "N_m3u8DL-RE.exe \"" + url + "\" --save-dir \"" + saveDir + "\" --save-name \"" + filename + "\" --check-segments-count False --binary-merge True";
            } else {
                command = "./N_m3u8DL-RE \"" + url + "\" --save-dir \"" + saveDir + "\" --save-name \"" + filename + "\" --check-segments-count False --binary-merge True";
            }
        } else {
            command = command.replace("{url}", url).replace("{filename}", filename).replace("{save_dir}", saveDir);
        }

        try {
            Process process = Runtime.getRuntime().exec(command);
            process.waitFor();
            if (process.exitValue() != 0) {
                throw new IOException("Failed to execute command: " + command);
            }
        } catch (IOException | InterruptedException e) {
            System.err.println("初次下载 " + filename + " 出错，重试中...");
            try {
                Process process = Runtime.getRuntime().exec(command);
                process.waitFor();
                if (process.exitValue() != 0) {
                    System.err.println("重试下载 " + filename + " 仍然出错，跳过此视频。");
                }
            } catch (IOException | InterruptedException ex) {
                System.err.println("重试下载 " + filename + " 仍然出错，跳过此视频。");
            }
        }
    }

    private static void createDirectory(String path) {
        try {
            Files.createDirectories(Paths.get(path));
        } catch (IOException e) {
            System.err.println("Failed to create directory: " + path);
        }
    }

    private static void writeCsv(String filename, List<String[]> rows) {
        try (BufferedWriter writer = Files.newBufferedWriter(Paths.get(filename), StandardCharsets.UTF_8, StandardOpenOption.CREATE)) {
            writer.write("month,date,day,jie,days,pptVideo,teacherTrack\n");
            for (String[] row : rows) {
                writer.write(String.join(",", row));
                writer.write("\n");
            }
        } catch (IOException e) {
            System.err.println("Failed to write CSV file: " + filename);
        }
    }

    private static String dayToChinese(int day) {
        String[] days = {"日", "一", "二", "三", "四", "五", "六"};
        return days[day];
    }

    private static String postRequest(String url, String params) {
        try {
            URL urlObj = new URL(url);
            HttpURLConnection conn = (HttpURLConnection) urlObj.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("User-Agent", "Mozilla/5.0");
            conn.setRequestProperty("Cookie", "UID=2");
            conn.setDoOutput(true);

            try (OutputStream os = conn.getOutputStream()) {
                byte[] input = params.getBytes(StandardCharsets.UTF_8);
                os.write(input, 0, input.length);
            }

            try (BufferedReader br = new BufferedReader(new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8))) {
                StringBuilder response = new StringBuilder();
                String responseLine;
                while ((responseLine = br.readLine()) != null) {
                    response.append(responseLine.trim());
                }
                return response.toString();
            }
        } catch (IOException e) {
            e.printStackTrace();
            return null;
        }
    }

    private static String getRequest(String url) {
        try {
            URL urlObj = new URL(url);
            HttpURLConnection conn = (HttpURLConnection) urlObj.openConnection();
            conn.setRequestMethod("GET");
            conn.setRequestProperty("User-Agent", "Mozilla/5.0");
            conn.setRequestProperty("Cookie", "UID=2");

            try (BufferedReader br = new BufferedReader(new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8))) {
                StringBuilder response = new StringBuilder();
                String responseLine;
                while ((responseLine = br.readLine()) != null) {
                    response.append(responseLine.trim());
                }
                return response.toString();
            }
        } catch (IOException e) {
            e.printStackTrace();
            return null;
        }
    }

    private static Arguments parseArguments(String[] args) {
        Arguments arguments = new Arguments();
        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "-c":
                case "--command":
                    if (i + 1 < args.length) {
                        arguments.command = args[++i];
                    } else {
                        System.err.println("Missing command argument");
                        return null;
                    }
                    break;
                case "-s":
                case "--single":
                    arguments.single = true;
                    break;
                default:
                    if (args[i].matches("\\d{1,10}")) {
                        arguments.liveId = args[i];
                    } else {
                        System.err.println("Unknown argument: " + args[i]);
                        return null;
                    }
            }
        }
        return arguments;
    }

    private static class Arguments {
        String liveId = null;
        String command = "";
        boolean single = false;
    }
}
